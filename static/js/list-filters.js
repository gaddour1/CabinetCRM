document.querySelectorAll(".js-live-list").forEach((form) => {
  const search = form.querySelector("[data-live-search]");
  const results = form.parentElement.querySelector("[data-live-results]");
  const rows = results?.querySelector("[data-live-rows]");
  const tableWrap = results?.querySelector(".table-wrap");
  const emptyState = results?.querySelector("[data-live-empty]");
  const status = form.querySelector(".live-list-status");
  const clearButton = form.querySelector("[data-live-clear]");
  const actions = form.querySelector("[data-live-actions]");

  if (!results || !rows || !tableWrap || !emptyState) return;

  let debounceTimer;
  let activeRequest;

  const updateResults = async () => {
    if (activeRequest) activeRequest.abort();
    const requestController = new AbortController();
    activeRequest = requestController;
    results.setAttribute("aria-busy", "true");

    const params = new URLSearchParams(new FormData(form));
    const pageUrl = new URL(form.action, window.location.origin);
    pageUrl.search = params.toString();
    const requestUrl = new URL(pageUrl);
    requestUrl.searchParams.set("partial", "1");

    if (status) status.textContent = "Recherche…";
    try {
      const response = await fetch(requestUrl, {
        headers: { Accept: "application/json" },
        signal: requestController.signal,
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      rows.innerHTML = data.rows;
      const hasRows = rows.children.length > 0;
      tableWrap.hidden = !hasRows;
      emptyState.hidden = hasRows;
      if (!hasRows) {
        const paragraph = emptyState.querySelector("p");
        if (paragraph) paragraph.textContent = results.dataset.emptyMessage;
      }

      window.history.replaceState({}, "", `${pageUrl.pathname}${pageUrl.search}`);
      if (status) status.textContent = `${data.count} résultat${data.count === 1 ? "" : "s"}`;
    } catch (error) {
      if (error.name === "AbortError") return;
      if (status) status.textContent = "La recherche a échoué. Réessayez.";
    } finally {
      if (activeRequest === requestController && !requestController.signal.aborted) {
        results.removeAttribute("aria-busy");
      }
    }
  };

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    window.clearTimeout(debounceTimer);
    updateResults();
  });

  form.querySelectorAll("[data-live-filter]").forEach((filter) => {
    filter.addEventListener("change", updateResults);
  });

  if (search) {
    search.addEventListener("input", () => {
      if (clearButton) clearButton.hidden = !search.value;
      if (actions) actions.hidden = !search.value;
      window.clearTimeout(debounceTimer);
      debounceTimer = window.setTimeout(updateResults, 300);
    });
  }

  if (clearButton && search) {
    clearButton.addEventListener("click", () => {
      search.value = "";
      clearButton.hidden = true;
      if (actions) actions.hidden = true;
      window.clearTimeout(debounceTimer);
      updateResults();
      search.focus();
    });
  }
});
