(() => {
  const form = document.querySelector("[data-medication-suggestions]");
  if (!form) return;

  const rows = form.querySelector("[data-medication-rows]");
  const template = form.querySelector("[data-empty-medication-form]");
  const totalForms = form.querySelector('[name="medications-TOTAL_FORMS"]');
  if (!rows || !template || !totalForms) return;

  const visibleRows = () =>
    [...rows.querySelectorAll("[data-medication-row]")].filter(
      (row) => row.querySelector('[name$="-DELETE"]')?.value !== "on",
    );

  const updateOrder = () => {
    visibleRows().forEach((row, index) => {
      const orderField = row.querySelector('[name$="-ORDER"]');
      if (orderField) orderField.value = String(index);
      const title = row.querySelector(".medication-card-title");
      if (title) title.textContent = `Médicament ${index + 1}`;
    });
  };

  const populateSuggestion = (input, suggestion) => {
    const prefix = input.name.slice(0, -"-name".length);
    for (const [field, value] of Object.entries(suggestion)) {
      const target = form.elements.namedItem(`${prefix}-${field}`);
      if (target && value !== null && value !== undefined) target.value = value;
    }
    input.dispatchEvent(new Event("change", { bubbles: true }));
  };

  const showSuggestions = (input, results) => {
    const list = input
      .closest("[data-medication-row]")
      ?.querySelector(".medication-suggestions");
    if (!list) return;
    list.replaceChildren();
    for (const suggestion of results) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "medication-suggestion";
      button.setAttribute("role", "option");
      button.textContent = [suggestion.name, suggestion.dosage].filter(Boolean).join(" — ");
      button.addEventListener("click", () => {
        populateSuggestion(input, suggestion);
        list.hidden = true;
      });
      list.append(button);
    }
    list.hidden = results.length === 0;
  };

  let searchTimer;
  form.addEventListener("input", (event) => {
    const input = event.target.closest('input[name$="-name"]');
    if (!input) return;
    const query = input.value.trim();
    const list = input
      .closest("[data-medication-row]")
      ?.querySelector(".medication-suggestions");
    if (list) list.hidden = true;
    window.clearTimeout(searchTimer);
    if (query.length < 2) return;

    searchTimer = window.setTimeout(async () => {
      try {
        const url = new URL(form.dataset.medicationSuggestions, window.location.origin);
        url.searchParams.set("q", query);
        const response = await fetch(url, {
          headers: { Accept: "application/json" },
        });
        if (!response.ok) throw new Error("Recherche de médicaments indisponible.");
        const payload = await response.json();
        showSuggestions(input, payload.results);
      } catch {
        if (list) {
          list.replaceChildren();
          const error = document.createElement("span");
          error.className = "medication-suggestion-error";
          error.textContent = "Les suggestions sont temporairement indisponibles.";
          list.append(error);
          list.hidden = false;
        }
      }
    }, 180);
  });

  rows.addEventListener("click", (event) => {
    const removeButton = event.target.closest("[data-remove-medication]");
    if (removeButton) {
      const row = removeButton.closest("[data-medication-row]");
      const deleteField = row?.querySelector('[name$="-DELETE"]');
      if (row && deleteField) {
        deleteField.value = "on";
        row.hidden = true;
        updateOrder();
      }
      return;
    }

    const moveButton = event.target.closest("[data-move-medication]");
    if (!moveButton) return;
    const row = moveButton.closest("[data-medication-row]");
    const activeRows = visibleRows();
    const index = activeRows.indexOf(row);
    if (index < 0) return;
    if (moveButton.dataset.moveMedication === "up" && index > 0) {
      rows.insertBefore(row, activeRows[index - 1]);
    } else if (
      moveButton.dataset.moveMedication === "down" &&
      index < activeRows.length - 1
    ) {
      rows.insertBefore(activeRows[index + 1], row);
    }
    updateOrder();
  });

  form.querySelector("[data-add-medication]")?.addEventListener("click", () => {
    const index = Number.parseInt(totalForms.value, 10);
    rows.insertAdjacentHTML(
      "beforeend",
      template.innerHTML.replace(/__prefix__/g, String(index)),
    );
    totalForms.value = String(index + 1);
    updateOrder();
    rows.lastElementChild
      ?.querySelector('input[name$="-name"]')
      ?.focus();
  });

  document.addEventListener("click", (event) => {
    if (event.target.closest(".medication-suggestions")) return;
    if (event.target.matches('input[name$="-name"]')) return;
    form.querySelectorAll(".medication-suggestions").forEach((list) => {
      list.hidden = true;
    });
  });

  updateOrder();
})();
