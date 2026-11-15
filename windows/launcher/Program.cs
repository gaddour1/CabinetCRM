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
        if (Environment.GetCommandLineArgs().Skip(1).Contains(
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
        ProcessStartInfo startInfo = new(docker)
        {
            WorkingDirectory = directory,
            UseShellExecute = false,
            CreateNoWindow = true,
        };
        startInfo.Environment["CABINET_ENV_FILE"] = environmentFile;
        foreach (string argument in new[]
        {
            "compose", "--env-file", environmentFile, "--project-directory", directory,
            "-f", Path.Combine(directory, "compose.yaml"), "down",
        })
        {
            startInfo.ArgumentList.Add(argument);
        }

        using Process? process = Process.Start(startInfo);
        process?.WaitForExit(TimeSpan.FromMinutes(2));
    }

    private static string? FindDockerForShutdown()
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
            EnsureEnvironmentFile();
            string docker = FindDocker();
            await WaitForDockerAsync(docker, _cancellation.Token);

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
            MessageBox.Show(
                this,
                error.Message,
                "Démarrage de Cabinet impossible",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
            Close();
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
        List<string> composeArguments =
        [
            "compose",
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
