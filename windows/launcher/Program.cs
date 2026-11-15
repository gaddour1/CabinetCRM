using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace CabinetLauncher;

internal static class Program
{
    [STAThread]
    private static void Main()
    {
        string[] arguments = Environment.GetCommandLineArgs().Skip(1).ToArray();
        if (arguments.Length > 0 && arguments[0].Equals(
                "--preupdate",
                StringComparison.OrdinalIgnoreCase))
        {
            ApplicationConfiguration.Initialize();
            try
            {
                CabinetPreUpdate.RunAsync(arguments.Skip(1).ToArray())
                    .GetAwaiter()
                    .GetResult();
            }
            catch (Exception error)
            {
                MessageBox.Show(
                    "La mise à jour est annulée. Aucun fichier applicatif n’a été remplacé.\n\n"
                    + error.Message
                    + "\n\nLes éventuels fichiers de sauvegarde sont conservés dans "
                    + Path.Combine(
                        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                        "Cabinet",
                        "backups"),
                    "Sauvegarde préalable impossible",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
                Environment.ExitCode = 1;
            }
            return;
        }

        if (arguments.Contains(
                "--stop",
                StringComparer.OrdinalIgnoreCase))
        {
            StopCabinetStack();
            return;
        }

        ApplicationConfiguration.Initialize();
        Application.Run(new StartupForm());
    }

    private static void StopCabinetStack()
    {
        string directory = AppContext.BaseDirectory;
        string? docker = FindDockerForShutdown();
        if (docker is null)
        {
            return;
        }

        string environmentFile = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "Cabinet",
            ".env");
        string projectFile = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "Cabinet",
            "compose-project-name.txt");
        ProcessStartInfo startInfo = new(docker)
        {
            WorkingDirectory = directory,
            UseShellExecute = false,
            CreateNoWindow = true,
        };
        startInfo.Environment["CABINET_ENV_FILE"] = environmentFile;
        List<string> arguments = ["compose"];
        if (File.Exists(projectFile))
        {
            string projectName = File.ReadAllText(projectFile).Trim();
            if (!string.IsNullOrWhiteSpace(projectName))
            {
                arguments.AddRange(["--project-name", projectName]);
            }
        }
        arguments.AddRange(
        [
            "--env-file",
            environmentFile,
            "--project-directory",
            directory,
            "-f",
            Path.Combine(directory, "compose.yaml"),
            "down",
        ]);
        foreach (string argument in arguments)
        {
            startInfo.ArgumentList.Add(argument);
        }

        using Process? process = Process.Start(startInfo);
        process?.WaitForExit(TimeSpan.FromMinutes(2));
    }

    internal static string? FindDockerForShutdown()
    {
        IEnumerable<string> pathCandidates = (
            Environment.GetEnvironmentVariable("PATH") ?? string.Empty)
            .Split(Path.PathSeparator, StringSplitOptions.RemoveEmptyEntries)
            .Select(directory => Path.Combine(directory.Trim('"'), "docker.exe"));
        string[] candidates =
        [
            .. pathCandidates,
            Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),
                "Docker",
                "Docker",
                "resources",
                "bin",
                "docker.exe"),
            Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86),
                "Docker",
                "Docker",
                "resources",
                "bin",
                "docker.exe"),
            Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "Programs",
                "Docker",
                "Docker",
                "resources",
                "bin",
                "docker.exe"),
        ];
        return candidates.FirstOrDefault(File.Exists);
    }
}

internal static class CabinetPreUpdate
{
    private const string DumpFile = "cabinet-v1-before-v2.dump";
    private const string GlobalsFile = "cabinet-v1-before-v2-globals.sql";
    private const string ContainerDumpPath = "/tmp/cabinet-v1-before-v2.dump";
    private const string ContainerGlobalsPath = "/tmp/cabinet-v1-before-v2-globals.sql";

    public static async Task RunAsync(string[] arguments)
    {
        if (arguments.Length != 2)
        {
            throw new InvalidOperationException(
                "Paramètres de mise à jour incomplets.");
        }

        string installDirectory = Path.GetFullPath(arguments[0]);
        string previousVersion = arguments[1];
        if (previousVersion.Any(character => !char.IsAsciiLetterOrDigit(character)
            && character != '.' && character != '-'))
        {
            throw new InvalidOperationException(
                "La version précédente de Cabinet est invalide.");
        }

        string dataDirectory = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "Cabinet");
        string environmentFile = Path.Combine(dataDirectory, ".env");
        string composeFile = Path.Combine(installDirectory, "compose.yaml");
        if (!File.Exists(environmentFile) || !File.Exists(composeFile))
        {
            throw new InvalidOperationException(
                "Installation existante ou fichier .env introuvable. "
                + "La mise à jour ne peut pas identifier la base à sauvegarder.");
        }

        string docker = Program.FindDockerForShutdown()
            ?? throw new FileNotFoundException(
                "Docker est introuvable. Installez ou démarrez Docker Desktop.");

        ProcessResult runningDatabase = await RunComposeAsync(
            docker,
            installDirectory,
            environmentFile,
            ["ps", "-q", "db"]);
        string containerId = runningDatabase.StandardOutput.Trim();
        if (string.IsNullOrWhiteSpace(containerId))
        {
            throw new InvalidOperationException(
                "PostgreSQL n’est pas démarré. Lancez d’abord Cabinet V1, "
                + "vérifiez que la connexion fonctionne, puis relancez la mise à jour.");
        }

        ProcessResult projectResult = await RunDockerAsync(
            docker,
            [
                "inspect",
                "--format",
                "{{ index .Config.Labels \"com.docker.compose.project\" }}",
                containerId,
            ]);
        string projectName = projectResult.StandardOutput.Trim();
        if (string.IsNullOrWhiteSpace(projectName))
        {
            throw new InvalidOperationException(
                "Impossible d’identifier le projet Docker Compose de cette installation.");
        }

        ProcessResult workingDirectoryResult = await RunDockerAsync(
            docker,
            [
                "inspect",
                "--format",
                "{{ index .Config.Labels \"com.docker.compose.project.working_dir\" }}",
                containerId,
            ]);
        if (!PathsEqual(workingDirectoryResult.StandardOutput.Trim(), installDirectory))
        {
            throw new InvalidOperationException(
                "Le conteneur PostgreSQL appartient à un autre dossier Compose. "
                + "Aucune mise à jour n’a été effectuée.");
        }

        ProcessResult volumeResult = await RunDockerAsync(
            docker,
            [
                "inspect",
                "--format",
                "{{range .Mounts}}{{if eq .Destination \"/var/lib/postgresql/data\"}}{{.Name}}{{end}}{{end}}",
                containerId,
            ]);
        string volumeName = volumeResult.StandardOutput.Trim();
        if (string.IsNullOrWhiteSpace(volumeName))
        {
            throw new InvalidOperationException(
                "Le volume PostgreSQL persistant de l’installation est introuvable.");
        }

        ProcessResult volumeProjectResult = await RunDockerAsync(
            docker,
            [
                "volume",
                "inspect",
                "--format",
                "{{ index .Labels \"com.docker.compose.project\" }}",
                volumeName,
            ]);
        if (!string.Equals(
                volumeProjectResult.StandardOutput.Trim(),
                projectName,
                StringComparison.Ordinal))
        {
            throw new InvalidOperationException(
                "Le volume PostgreSQL ne correspond pas au projet Compose détecté.");
        }

        await RunComposeAsync(
            docker,
            installDirectory,
            environmentFile,
            [
                "exec",
                "-T",
                "db",
                "sh",
                "-c",
                "set -eu; pg_isready -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\"; "
                + "test \"$(psql -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\" -Atc "
                + "\"SELECT to_regclass('public.billing_invoice') IS NOT NULL "
                + "AND to_regclass('public.billing_payment') IS NOT NULL\")\" = t",
            ],
            projectName: projectName);

        string backupDirectory = Path.Combine(dataDirectory, "backups");
        Directory.CreateDirectory(backupDirectory);
        string timestamp = DateTime.Now.ToString(
            "yyyyMMdd-HHmmss",
            System.Globalization.CultureInfo.InvariantCulture);
        string dumpPath = Path.Combine(backupDirectory, $"{timestamp}-{DumpFile}");
        string globalsPath = Path.Combine(
            backupDirectory,
            $"{timestamp}-{GlobalsFile}");

        await RunComposeAsync(
                docker,
                installDirectory,
                environmentFile,
                [
                    "exec",
                    "-T",
                    "db",
                    "sh",
                    "-c",
                    $"set -eu; pg_dump -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\" "
                    + $"--format=custom --no-owner --no-acl --file={ContainerDumpPath}; "
                    + $"pg_restore --list {ContainerDumpPath} > /tmp/cabinet-v1-before-v2.list; "
                    + "pg_dumpall --globals-only -U \"$POSTGRES_USER\" "
                    + $"> {ContainerGlobalsPath}; "
                    + $"test -s {ContainerDumpPath}; test -s {ContainerGlobalsPath}",
                ],
                TimeSpan.FromMinutes(30),
                projectName);

            await RunDockerAsync(
                    docker,
                    ["cp", $"{containerId}:{ContainerDumpPath}", dumpPath],
                    TimeSpan.FromMinutes(5));
            await RunDockerAsync(
                    docker,
                    ["cp", $"{containerId}:{ContainerGlobalsPath}", globalsPath],
                    TimeSpan.FromMinutes(5));

            VerifyBackupFile(dumpPath);
            VerifyBackupFile(globalsPath);
            string globalsContent = await File.ReadAllTextAsync(globalsPath);
            if (!globalsContent.Contains("CREATE ROLE", StringComparison.Ordinal))
            {
                throw new InvalidOperationException(
                    "La sauvegarde des rôles PostgreSQL est vide ou invalide.");
            }

            string dumpHash = await ComputeSha256Async(dumpPath);
            string globalsHash = await ComputeSha256Async(globalsPath);
            string projectFile = Path.Combine(dataDirectory, "compose-project-name.txt");
            string volumeFile = Path.Combine(dataDirectory, "postgres-volume-name.txt");
            await File.WriteAllTextAsync(projectFile, projectName + Environment.NewLine);
            File.SetAttributes(
                projectFile,
                File.GetAttributes(projectFile) | FileAttributes.Hidden);
            await File.WriteAllTextAsync(volumeFile, volumeName + Environment.NewLine);
            File.SetAttributes(
                volumeFile,
                File.GetAttributes(volumeFile) | FileAttributes.Hidden);

            var manifest = new
            {
                PreviousVersion = previousVersion,
                TargetVersion = "2.0.0",
                CreatedAt = DateTimeOffset.Now,
                ComposeProject = projectName,
                PostgresVolume = volumeName,
                DatabaseDump = Path.GetFileName(dumpPath),
                DatabaseDumpSha256 = dumpHash,
                GlobalsDump = Path.GetFileName(globalsPath),
                GlobalsDumpSha256 = globalsHash,
            };
            await File.WriteAllTextAsync(
                Path.Combine(backupDirectory, $"{timestamp}-manifest.json"),
                JsonSerializer.Serialize(
                    manifest,
                    new JsonSerializerOptions { WriteIndented = true }));

            await RunComposeAsync(
                docker,
                installDirectory,
                environmentFile,
                [
                    "exec",
                    "-T",
                    "db",
                    "sh",
                    "-c",
                    $"rm -f {ContainerDumpPath} {ContainerGlobalsPath} "
                    + "/tmp/cabinet-v1-before-v2.list",
                ],
                projectName: projectName);
            await RunComposeAsync(
                docker,
                installDirectory,
                environmentFile,
                ["stop"],
                TimeSpan.FromMinutes(5),
                projectName);

        MessageBox.Show(
            $"Sauvegarde PostgreSQL vérifiée :\n{dumpPath}\n\n"
            + "La base et les rôles sont sauvegardés hors du volume Docker. "
            + "Les services sont arrêtés proprement; l’installation peut continuer.",
            "Cabinet V2 — sauvegarde terminée",
            MessageBoxButtons.OK,
            MessageBoxIcon.Information);
    }

    private static bool PathsEqual(string left, string right)
    {
        static string Normalize(string path) =>
            Path.GetFullPath(path).TrimEnd(
                Path.DirectorySeparatorChar,
                Path.AltDirectorySeparatorChar);

        return string.Equals(Normalize(left), Normalize(right), StringComparison.OrdinalIgnoreCase);
    }

    private static void VerifyBackupFile(string path)
    {
        var file = new FileInfo(path);
        if (!file.Exists || file.Length == 0)
        {
            throw new InvalidOperationException(
                $"Le fichier de sauvegarde est absent ou vide : {path}");
        }
    }

    private static async Task<string> ComputeSha256Async(string path)
    {
        await using FileStream stream = File.OpenRead(path);
        byte[] hash = await SHA256.HashDataAsync(stream);
        return Convert.ToHexString(hash);
    }

    private static Task<ProcessResult> RunComposeAsync(
        string docker,
        string installDirectory,
        string environmentFile,
        IEnumerable<string> arguments,
        TimeSpan? timeout = null,
        string? projectName = null)
    {
        List<string> composeArguments = ["compose"];
        if (!string.IsNullOrWhiteSpace(projectName))
        {
            composeArguments.AddRange(["--project-name", projectName]);
        }
        composeArguments.AddRange(
        [
            "--env-file",
            environmentFile,
            "--project-directory",
            installDirectory,
            "-f",
            Path.Combine(installDirectory, "compose.yaml"),
        ]);
        composeArguments.AddRange(arguments);
        return RunDockerAsync(
            docker,
            composeArguments,
            timeout ?? TimeSpan.FromMinutes(2),
            installDirectory,
            environmentFile);
    }

    private static async Task<ProcessResult> RunDockerAsync(
        string docker,
        IEnumerable<string> arguments,
        TimeSpan? timeout = null,
        string? workingDirectory = null,
        string? environmentFile = null)
    {
        ProcessStartInfo startInfo = new(docker)
        {
            WorkingDirectory = workingDirectory ?? Environment.CurrentDirectory,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
        };
        if (environmentFile is not null)
        {
            startInfo.Environment["CABINET_ENV_FILE"] = environmentFile;
        }
        foreach (string argument in arguments)
        {
            startInfo.ArgumentList.Add(argument);
        }

        using Process process = new() { StartInfo = startInfo };
        if (!process.Start())
        {
            throw new InvalidOperationException("Impossible de démarrer Docker.");
        }

        Task<string> outputTask = process.StandardOutput.ReadToEndAsync();
        Task<string> errorTask = process.StandardError.ReadToEndAsync();
        using CancellationTokenSource timeoutSource = new(timeout ?? TimeSpan.FromMinutes(2));
        try
        {
            await process.WaitForExitAsync(timeoutSource.Token);
        }
        catch (OperationCanceledException)
        {
            if (!process.HasExited)
            {
                process.Kill(entireProcessTree: true);
            }
            throw new TimeoutException(
                $"La commande {Path.GetFileName(docker)} a expiré.");
        }

        string standardOutput = await outputTask;
        string standardError = await errorTask;
        if (process.ExitCode != 0)
        {
            string detail = string.IsNullOrWhiteSpace(standardError)
                ? standardOutput.Trim()
                : standardError.Trim();
            throw new InvalidOperationException(
                $"La commande Docker a échoué ({process.ExitCode}). {detail}");
        }

        return new ProcessResult(standardOutput, standardError);
    }

    private sealed record ProcessResult(string StandardOutput, string StandardError);
}

internal sealed class StartupForm : Form
{
    private const string ApplicationUrl = "http://127.0.0.1:8001/connexion/";
    private readonly Label _status = new();
    private readonly ProgressBar _progress = new();
    private readonly CancellationTokenSource _cancellation = new();
    private readonly string _applicationDirectory = AppContext.BaseDirectory;
    private readonly string _dataDirectory = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "Cabinet");
    private readonly string _composeProjectFile = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "Cabinet",
        "compose-project-name.txt");
    private readonly string _postgresVolumeFile = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "Cabinet",
        "postgres-volume-name.txt");

    public StartupForm()
    {
        Text = "Cabinet";
        Width = 480;
        Height = 155;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        MinimizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;
        ShowInTaskbar = true;

        _status.Dock = DockStyle.Top;
        _status.Height = 62;
        _status.Padding = new Padding(18);
        _status.Font = new Font("Segoe UI", 11);
        _status.Text = "Préparation de Cabinet...";

        _progress.Dock = DockStyle.Bottom;
        _progress.Height = 18;
        _progress.Style = ProgressBarStyle.Marquee;
        _progress.MarqueeAnimationSpeed = 24;
        Controls.Add(_progress);
        Controls.Add(_status);

        Shown += async (_, _) => await StartCabinetAsync();
        FormClosed += (_, _) => _cancellation.Cancel();
    }

    private async Task StartCabinetAsync()
    {
        try
        {
            EnsureDeploymentFiles();
            string docker = FindDocker();
            await WaitForDockerAsync(docker, _cancellation.Token);
            EnsureEnvironmentFile();
            await EnsureExpectedDatabaseVolumeAsync(docker, _cancellation.Token);

            SetStatus("Vérification du volume PostgreSQL...");
            await RunDockerAsync(
                docker,
                ["compose", "up", "-d", "db"],
                TimeSpan.FromMinutes(5),
                _cancellation.Token);
            await VerifyAndSaveDatabaseVolumeAsync(docker, _cancellation.Token);

            SetStatus("Démarrage de PostgreSQL et du cabinet...");
            await RunDockerAsync(
                docker,
                ["compose", "up", "--build", "-d"],
                TimeSpan.FromMinutes(20),
                _cancellation.Token);

            await WaitForApplicationAsync(_cancellation.Token);
            await CreateFirstDoctorIfRequiredAsync(docker, _cancellation.Token);
            OpenEdge();
            Close();
        }
        catch (OperationCanceledException)
        {
            Close();
        }
        catch (Exception error)
        {
            string backupDirectory = Path.Combine(_dataDirectory, "backups");
            string backupNotice = Directory.Exists(backupDirectory)
                ? $"\n\nAucune restauration automatique n’a été effectuée. "
                  + $"Conservez les sauvegardes de {backupDirectory}."
                : string.Empty;
            MessageBox.Show(
                this,
                error.Message + backupNotice,
                "Démarrage de Cabinet impossible",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
            Close();
        }
    }

    private async Task EnsureExpectedDatabaseVolumeAsync(
        string docker,
        CancellationToken cancellationToken)
    {
        bool hasProject = File.Exists(_composeProjectFile);
        bool hasVolume = File.Exists(_postgresVolumeFile);
        if (hasProject != hasVolume)
        {
            throw new InvalidOperationException(
                "Les informations du projet et du volume PostgreSQL sont incomplètes. "
                + "Aucun nouveau volume ne sera créé.");
        }

        ProcessResult configuration = await RunDockerAsync(
            docker,
            ["compose", "config", "--format", "json"],
            TimeSpan.FromSeconds(30),
            cancellationToken);
        using JsonDocument document = JsonDocument.Parse(configuration.StandardOutput);
        string configuredVolume = document.RootElement
            .GetProperty("volumes")
            .GetProperty("postgres_data")
            .GetProperty("name")
            .GetString()
            ?? throw new InvalidOperationException(
                "Compose n’a pas fourni le nom effectif du volume PostgreSQL.");
        ProcessResult result = await RunProcessAsync(
            docker,
            ["volume", "ls", "--format", "{{.Name}}"],
            _applicationDirectory,
            TimeSpan.FromSeconds(30),
            cancellationToken);

        string[] volumes = result.StandardOutput
            .Split(Environment.NewLine, StringSplitOptions.RemoveEmptyEntries)
            .Select(name => name.Trim())
            .ToArray();
        if (hasVolume)
        {
            string expectedVolume = (await File.ReadAllTextAsync(_postgresVolumeFile)).Trim();
            if (string.IsNullOrWhiteSpace(expectedVolume)
                || !string.Equals(
                    configuredVolume,
                    expectedVolume,
                    StringComparison.Ordinal)
                || !volumes.Contains(expectedVolume, StringComparer.Ordinal))
            {
                throw new InvalidOperationException(
                    "Le volume PostgreSQL enregistré est absent ou différent du volume "
                    + "configuré. Aucun nouveau volume ne sera utilisé.");
            }
        }
        else if (volumes.Contains(configuredVolume, StringComparer.Ordinal))
        {
            throw new InvalidOperationException(
                $"Le volume PostgreSQL {configuredVolume} existe mais son identité n’est "
                + "pas enregistrée. Cabinet refuse de démarrer sur une base inconnue.");
        }
    }

    private async Task VerifyAndSaveDatabaseVolumeAsync(
        string docker,
        CancellationToken cancellationToken)
    {
        ProcessResult database = await RunDockerAsync(
            docker,
            ["compose", "ps", "-q", "db"],
            TimeSpan.FromSeconds(30),
            cancellationToken);
        string containerId = database.StandardOutput.Trim();
        if (string.IsNullOrWhiteSpace(containerId))
        {
            throw new InvalidOperationException(
                "Le conteneur PostgreSQL est introuvable après le démarrage.");
        }

        ProcessResult configuration = await RunDockerAsync(
            docker,
            ["compose", "config", "--format", "json"],
            TimeSpan.FromSeconds(30),
            cancellationToken);
        using JsonDocument document = JsonDocument.Parse(configuration.StandardOutput);
        string configuredVolume = document.RootElement
            .GetProperty("volumes")
            .GetProperty("postgres_data")
            .GetProperty("name")
            .GetString()
            ?? throw new InvalidOperationException(
                "Compose n’a pas fourni le nom effectif du volume PostgreSQL.");
        ProcessResult volume = await RunProcessAsync(
            docker,
            [
                "inspect",
                "--format",
                "{{range .Mounts}}{{if eq .Destination \"/var/lib/postgresql/data\"}}{{.Name}}{{end}}{{end}}",
                containerId,
            ],
            _applicationDirectory,
            TimeSpan.FromSeconds(30),
            cancellationToken);
        string volumeName = volume.StandardOutput.Trim();
        if (string.IsNullOrWhiteSpace(volumeName))
        {
            throw new InvalidOperationException(
                "Le conteneur PostgreSQL ne monte pas de volume de données persistant.");
        }
        if (!string.Equals(configuredVolume, volumeName, StringComparison.Ordinal))
        {
            throw new InvalidOperationException(
                $"PostgreSQL utilise le volume {volumeName}, différent du volume "
                + $"configuré {configuredVolume}. Aucun changement de base n’est autorisé.");
        }

        ProcessResult project = await RunProcessAsync(
            docker,
            [
                "inspect",
                "--format",
                "{{ index .Config.Labels \"com.docker.compose.project\" }}",
                containerId,
            ],
            _applicationDirectory,
            TimeSpan.FromSeconds(30),
            cancellationToken);
        string projectName = project.StandardOutput.Trim();
        ProcessResult volumeProject = await RunProcessAsync(
            docker,
            [
                "volume",
                "inspect",
                "--format",
                "{{ index .Labels \"com.docker.compose.project\" }}",
                volumeName,
            ],
            _applicationDirectory,
            TimeSpan.FromSeconds(30),
            cancellationToken);
        if (!string.Equals(
                volumeProject.StandardOutput.Trim(),
                projectName,
                StringComparison.Ordinal))
        {
            throw new InvalidOperationException(
                "Le volume PostgreSQL ne correspond pas au projet Compose.");
        }

        if (File.Exists(_composeProjectFile))
        {
            string expectedProject = (await File.ReadAllTextAsync(_composeProjectFile)).Trim();
            if (!string.Equals(expectedProject, projectName, StringComparison.Ordinal))
            {
                throw new InvalidOperationException(
                    $"Le projet Docker Compose a changé de {expectedProject} à "
                    + $"{projectName}. Aucun démarrage sur une nouvelle base n’est autorisé.");
            }
        }
        else if (!string.Equals(projectName, "cabinet", StringComparison.Ordinal))
        {
            throw new InvalidOperationException(
                "Le projet Docker Compose ne correspond pas au nom attendu pour une "
                + "première installation. Aucun changement de base n’est autorisé.");
        }
        if (File.Exists(_postgresVolumeFile))
        {
            string expectedVolume = (await File.ReadAllTextAsync(_postgresVolumeFile)).Trim();
            if (!string.Equals(expectedVolume, volumeName, StringComparison.Ordinal))
            {
                throw new InvalidOperationException(
                    $"Le volume PostgreSQL a changé de {expectedVolume} à {volumeName}. "
                    + "Aucun changement de base n’est autorisé.");
            }
        }
        else
        {
            await File.WriteAllTextAsync(
                _postgresVolumeFile,
                volumeName + Environment.NewLine);
            File.SetAttributes(
                _postgresVolumeFile,
                File.GetAttributes(_postgresVolumeFile) | FileAttributes.Hidden);
        }

        if (!File.Exists(_composeProjectFile))
        {
            await File.WriteAllTextAsync(
                _composeProjectFile,
                projectName + Environment.NewLine);
            File.SetAttributes(
                _composeProjectFile,
                File.GetAttributes(_composeProjectFile) | FileAttributes.Hidden);
        }
    }

    private void EnsureDeploymentFiles()
    {
        if (!File.Exists(Path.Combine(_applicationDirectory, "compose.yaml")) ||
            !File.Exists(Path.Combine(_applicationDirectory, "Dockerfile")))
        {
            throw new InvalidOperationException(
                "Les fichiers du cabinet sont incomplets. Réinstallez Cabinet.");
        }
    }

    private void EnsureEnvironmentFile()
    {
        Directory.CreateDirectory(_dataDirectory);
        string environmentFile = Path.Combine(_dataDirectory, ".env");
        if (File.Exists(environmentFile))
        {
            return;
        }

        string djangoSecret = CreateSecret(64);
        string databasePassword = CreateSecret(40);
        string contents = string.Join(
            Environment.NewLine,
            [
                $"DJANGO_SECRET_KEY={djangoSecret}",
                "DJANGO_DEBUG=False",
                "DJANGO_SECURE_COOKIES=False",
                "DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1",
                "DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:8001,http://127.0.0.1:8001",
                "POSTGRES_DB=cabinet",
                "POSTGRES_USER=cabinet_app",
                $"POSTGRES_PASSWORD={databasePassword}",
                "DB_HOST=db",
                "DB_PORT=5432",
                string.Empty,
            ]);

        File.WriteAllText(environmentFile, contents, new UTF8Encoding(false));
        File.SetAttributes(environmentFile, File.GetAttributes(environmentFile) | FileAttributes.Hidden);
    }

    private static string CreateSecret(int byteCount)
    {
        return Convert.ToBase64String(RandomNumberGenerator.GetBytes(byteCount))
            .Replace("+", string.Empty, StringComparison.Ordinal)
            .Replace("/", string.Empty, StringComparison.Ordinal)
            .Replace("=", string.Empty, StringComparison.Ordinal);
    }

    private static string FindDocker()
    {
        IEnumerable<string> pathCandidates = (
            Environment.GetEnvironmentVariable("PATH") ?? string.Empty)
            .Split(Path.PathSeparator, StringSplitOptions.RemoveEmptyEntries)
            .Select(directory => Path.Combine(directory.Trim('"'), "docker.exe"));
        string[] candidates =
        [
            .. pathCandidates,
            Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),
                "Docker",
                "Docker",
                "resources",
                "bin",
                "docker.exe"),
            Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86),
                "Docker",
                "Docker",
                "resources",
                "bin",
                "docker.exe"),
            Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "Programs",
                "Docker",
                "Docker",
                "resources",
                "bin",
                "docker.exe"),
        ];
        string? docker = candidates.FirstOrDefault(File.Exists);
        return docker ?? throw new FileNotFoundException(
            "La commande Docker est introuvable. Installez Docker Desktop puis relancez Cabinet.");
    }

    private async Task WaitForDockerAsync(string docker, CancellationToken cancellationToken)
    {
        SetStatus("Attente du moteur Docker...");
        if (await IsDockerReadyAsync(docker, cancellationToken))
        {
            return;
        }

        StartDockerDesktop();
        DateTime deadline = DateTime.UtcNow.AddMinutes(5);
        while (DateTime.UtcNow < deadline)
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (await IsDockerReadyAsync(docker, cancellationToken))
            {
                return;
            }

            await Task.Delay(TimeSpan.FromSeconds(5), cancellationToken);
        }

        throw new TimeoutException(
            "Docker n’est pas devenu prêt. Vérifiez que Docker Desktop est installé, "
            + "démarré et configuré pour les conteneurs Linux.");
    }

    private async Task<bool> IsDockerReadyAsync(
        string docker,
        CancellationToken cancellationToken)
    {
        try
        {
            await RunProcessAsync(
                docker,
                ["info", "--format", "{{.ServerVersion}}"],
                _applicationDirectory,
                TimeSpan.FromSeconds(12),
                cancellationToken);
            return true;
        }
        catch (Exception error) when (
            error is InvalidOperationException or TimeoutException or IOException)
        {
            return false;
        }
    }

    private static void StartDockerDesktop()
    {
        string[] candidates =
        [
            Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),
                "Docker",
                "Docker",
                "Docker Desktop.exe"),
            Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86),
                "Docker",
                "Docker",
                "Docker Desktop.exe"),
            Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "Programs",
                "Docker",
                "Docker",
                "Docker Desktop.exe"),
        ];
        string? desktop = candidates.FirstOrDefault(File.Exists);
        if (desktop is null)
        {
            throw new FileNotFoundException(
                "Docker Desktop n’est pas installé. Installez-le puis relancez Cabinet.");
        }

        Process[] desktopProcesses = Process.GetProcessesByName("Docker Desktop");
        try
        {
            if (desktopProcesses.Length > 0)
            {
                return;
            }
        }
        finally
        {
            foreach (Process process in desktopProcesses)
            {
                process.Dispose();
            }
        }

        Process.Start(new ProcessStartInfo(desktop) { UseShellExecute = true });
    }

    private async Task WaitForApplicationAsync(CancellationToken cancellationToken)
    {
        SetStatus("Attente du démarrage du cabinet...");
        using HttpClient client = new() { Timeout = TimeSpan.FromSeconds(5) };
        DateTime deadline = DateTime.UtcNow.AddMinutes(5);
        while (DateTime.UtcNow < deadline)
        {
            cancellationToken.ThrowIfCancellationRequested();
            try
            {
                using HttpResponseMessage response = await client.GetAsync(
                    ApplicationUrl,
                    cancellationToken);
                if (response.IsSuccessStatusCode)
                {
                    return;
                }
            }
            catch (HttpRequestException)
            {
            }
            catch (TaskCanceledException) when (!cancellationToken.IsCancellationRequested)
            {
            }

            await Task.Delay(TimeSpan.FromSeconds(3), cancellationToken);
        }

        throw new TimeoutException(
            "Le serveur du cabinet ne répond pas. Vérifiez l’état Docker Desktop.");
    }

    private async Task CreateFirstDoctorIfRequiredAsync(
        string docker,
        CancellationToken cancellationToken)
    {
        SetStatus("Vérification du compte médecin...");
        ProcessResult result = await RunDockerAsync(
            docker,
            [
                "compose", "exec", "-T", "web", "python", "manage.py",
                "initialize_clinic_doctor", "--check",
            ],
            TimeSpan.FromMinutes(1),
            cancellationToken);

        if (!result.StandardOutput.Contains(
                "CABINET_DOCTOR_REQUIRED=1",
                StringComparison.Ordinal))
        {
            return;
        }

        Hide();
        using InitialDoctorDialog dialog = new();
        while (dialog.ShowDialog(this) == DialogResult.OK)
        {
            try
            {
                SetStatus("Création du compte médecin...");
                string json = JsonSerializer.Serialize(dialog.Credentials);
                await RunDockerAsync(
                    docker,
                    [
                        "compose", "exec", "-T", "web", "python", "manage.py",
                        "initialize_clinic_doctor",
                    ],
                    TimeSpan.FromMinutes(1),
                    cancellationToken,
                    json);

                Show();
                return;
            }
            catch (Exception error) when (
                error is InvalidOperationException or TimeoutException or IOException)
            {
                Show();
                MessageBox.Show(
                    this,
                    error.Message,
                    "Création du compte médecin impossible",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
                Hide();
            }
        }

        throw new OperationCanceledException();
    }

    private void OpenEdge()
    {
        string[] candidates =
        [
            Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86),
                "Microsoft",
                "Edge",
                "Application",
                "msedge.exe"),
            Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),
                "Microsoft",
                "Edge",
                "Application",
                "msedge.exe"),
            Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "Microsoft",
                "Edge",
                "Application",
                "msedge.exe"),
        ];
        string? edge = candidates.FirstOrDefault(File.Exists);
        if (edge is null)
        {
            throw new FileNotFoundException(
                "Microsoft Edge est introuvable. Installez Edge puis relancez Cabinet.");
        }

        Process.Start(new ProcessStartInfo(edge)
        {
            UseShellExecute = false,
            ArgumentList = { $"--app={ApplicationUrl}" },
        });
    }

    private async Task<ProcessResult> RunDockerAsync(
        string docker,
        IEnumerable<string> arguments,
        TimeSpan timeout,
        CancellationToken cancellationToken,
        string? standardInput = null)
    {
        string environmentFile = Path.Combine(_dataDirectory, ".env");
        string projectName = "cabinet";
        if (File.Exists(_composeProjectFile))
        {
            projectName = (await File.ReadAllTextAsync(_composeProjectFile)).Trim();
            if (string.IsNullOrWhiteSpace(projectName))
            {
                throw new InvalidOperationException(
                    "Le nom du projet Docker Compose enregistré est vide.");
            }
        }
        List<string> composeArguments =
        [
            "compose",
            "--project-name",
            projectName,
            "--env-file",
            environmentFile,
            "--project-directory",
            _applicationDirectory,
            "-f",
            Path.Combine(_applicationDirectory, "compose.yaml"),
        ];
        composeArguments.AddRange(arguments.Skip(1));
        return await RunProcessAsync(
            docker,
            composeArguments,
            _applicationDirectory,
            timeout,
            cancellationToken,
            standardInput);
    }

    private static async Task<ProcessResult> RunProcessAsync(
        string executable,
        IEnumerable<string> arguments,
        string workingDirectory,
        TimeSpan timeout,
        CancellationToken cancellationToken,
        string? standardInput = null)
    {
        ProcessStartInfo startInfo = new(executable)
        {
            WorkingDirectory = workingDirectory,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            RedirectStandardInput = standardInput is not null,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
        };
        if (Path.GetFileName(executable).Equals("docker.exe", StringComparison.OrdinalIgnoreCase))
        {
            string environmentFile = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "Cabinet",
                ".env");
            startInfo.Environment["CABINET_ENV_FILE"] = environmentFile;
        }
        foreach (string argument in arguments)
        {
            startInfo.ArgumentList.Add(argument);
        }

        using Process process = new() { StartInfo = startInfo };
        if (!process.Start())
        {
            throw new InvalidOperationException("Impossible de démarrer Docker.");
        }

        Task<string> outputTask = process.StandardOutput.ReadToEndAsync(cancellationToken);
        Task<string> errorTask = process.StandardError.ReadToEndAsync(cancellationToken);
        if (standardInput is not null)
        {
            await process.StandardInput.WriteAsync(standardInput.AsMemory(), cancellationToken);
            process.StandardInput.Close();
        }

        using CancellationTokenSource timeoutSource =
            CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeoutSource.CancelAfter(timeout);
        try
        {
            await process.WaitForExitAsync(timeoutSource.Token);
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            if (!process.HasExited)
            {
                process.Kill(entireProcessTree: true);
            }
            throw new TimeoutException($"La commande {Path.GetFileName(executable)} a expiré.");
        }
        catch (OperationCanceledException)
        {
            if (!process.HasExited)
            {
                process.Kill(entireProcessTree: true);
            }
            throw;
        }

        string standardOutput = await outputTask;
        string standardError = await errorTask;
        if (process.ExitCode != 0)
        {
            string detail = string.IsNullOrWhiteSpace(standardError)
                ? standardOutput.Trim()
                : standardError.Trim();
            throw new InvalidOperationException(
                $"La commande Docker a échoué ({process.ExitCode}). {detail}");
        }

        return new ProcessResult(standardOutput, standardError);
    }

    private void SetStatus(string message)
    {
        if (InvokeRequired)
        {
            BeginInvoke((Action)(() => SetStatus(message)));
            return;
        }

        _status.Text = message;
    }

    private sealed record ProcessResult(string StandardOutput, string StandardError);
}

internal sealed class InitialDoctorDialog : Form
{
    private readonly TextBox _username = new() { Text = "medecin" };
    private readonly TextBox _firstName = new();
    private readonly TextBox _lastName = new();
    private readonly TextBox _password = new() { UseSystemPasswordChar = true };
    private readonly TextBox _confirmPassword = new() { UseSystemPasswordChar = true };

    public InitialDoctorDialog()
    {
        Text = "Créer le premier compte médecin";
        Width = 460;
        Height = 380;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        MinimizeBox = false;
        StartPosition = FormStartPosition.CenterParent;

        TableLayoutPanel fields = new()
        {
            Dock = DockStyle.Fill,
            Padding = new Padding(18),
            ColumnCount = 2,
            RowCount = 6,
        };
        fields.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 145));
        fields.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        for (int row = 0; row < 5; row++)
        {
            fields.RowStyles.Add(new RowStyle(SizeType.Absolute, 42));
        }
        fields.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        AddField(fields, 0, "Nom d’utilisateur", _username);
        AddField(fields, 1, "Prénom", _firstName);
        AddField(fields, 2, "Nom", _lastName);
        AddField(fields, 3, "Mot de passe", _password);
        AddField(fields, 4, "Confirmer le mot de passe", _confirmPassword);

        Label note = new()
        {
            Text = "Mot de passe : 8 caractères minimum. Évitez les mots courants, "
                + "les mots de passe uniquement numériques et ceux contenant vos "
                + "informations personnelles.",
            Dock = DockStyle.Fill,
            ForeColor = Color.DimGray,
            TextAlign = ContentAlignment.MiddleLeft,
        };
        fields.Controls.Add(note, 0, 5);
        fields.SetColumnSpan(note, 2);

        Button create = new() { Text = "Créer le compte", DialogResult = DialogResult.None };
        Button cancel = new() { Text = "Annuler", DialogResult = DialogResult.Cancel };
        FlowLayoutPanel buttons = new()
        {
            Dock = DockStyle.Bottom,
            Height = 48,
            FlowDirection = FlowDirection.RightToLeft,
            Padding = new Padding(8),
        };
        buttons.Controls.Add(create);
        buttons.Controls.Add(cancel);
        Controls.Add(fields);
        Controls.Add(buttons);
        AcceptButton = create;
        CancelButton = cancel;
        create.Click += (_, _) => ValidateAndAccept();
    }

    public object Credentials => new
    {
        username = _username.Text.Trim(),
        first_name = _firstName.Text.Trim(),
        last_name = _lastName.Text.Trim(),
        password = _password.Text,
    };

    private static void AddField(
        TableLayoutPanel panel,
        int row,
        string label,
        TextBox input)
    {
        panel.Controls.Add(
            new Label { Text = label, AutoSize = true, Anchor = AnchorStyles.Left },
            0,
            row);
        input.Dock = DockStyle.Fill;
        panel.Controls.Add(input, 1, row);
    }

    private void ValidateAndAccept()
    {
        if (string.IsNullOrWhiteSpace(_username.Text) ||
            string.IsNullOrWhiteSpace(_password.Text))
        {
            ShowValidationError("Le nom d’utilisateur et le mot de passe sont obligatoires.");
            return;
        }

        if (!string.Equals(_password.Text, _confirmPassword.Text, StringComparison.Ordinal))
        {
            ShowValidationError("Les deux mots de passe ne correspondent pas.");
            return;
        }

        DialogResult = DialogResult.OK;
    }

    private void ShowValidationError(string message)
    {
        MessageBox.Show(
            this,
            message,
            "Compte médecin",
            MessageBoxButtons.OK,
            MessageBoxIcon.Warning);
    }
}
