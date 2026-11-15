(() => {
  const form = document.querySelector(".consultation-form[data-suggestions-url]");
  if (!form) return;

  const cache = new Map();
  const csrfToken = form.querySelector("[name=csrfmiddlewaretoken]")?.value;
  const normalize = (value) =>
    value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase().trim();

  class SuggestionDropdown {
    constructor(input, category, container, onSelect) {
      this.input = input;
      this.category = category;
      this.container = container;
      this.onSelect = onSelect;
      this.activeIndex = -1;
      this.suggestions = [];
      this.controller = null;
      this.timer = null;

      container.classList.add("autocomplete-container");
      this.menu = document.createElement("div");
      this.menu.className = "autocomplete-list";
      this.menu.id = `${input.id || "medical-input"}-suggestions`;
      this.menu.setAttribute("role", "listbox");
      this.menu.hidden = true;
      container.append(this.menu);

      this.status = document.createElement("div");
      this.status.className = "autocomplete-status";
      this.status.setAttribute("role", "status");
      this.status.hidden = true;
      container.append(this.status);

      input.setAttribute("role", "combobox");
      input.setAttribute("aria-autocomplete", "list");
      input.setAttribute("aria-expanded", "false");
      input.setAttribute("aria-controls", this.menu.id);

      input.addEventListener("focus", () => this.scheduleLoad());
      input.addEventListener("input", () => this.scheduleLoad());
      input.addEventListener("keydown", (event) => this.handleKeydown(event));
      window.addEventListener("resize", () => this.positionMenu());
      document.addEventListener("pointerdown", (event) => {
        if (!container.contains(event.target)) this.close();
      });
    }

    positionMenu() {
      this.menu.style.top = `${this.container.offsetHeight + 4}px`;
    }

    close() {
      this.menu.hidden = true;
      this.input.setAttribute("aria-expanded", "false");
      this.input.removeAttribute("aria-activedescendant");
      this.activeIndex = -1;
    }

    scheduleLoad() {
      this.controller?.abort();
      this.close();
      this.status.hidden = true;
      window.clearTimeout(this.timer);
      this.timer = window.setTimeout(() => this.load(), 250);
    }

    async load() {
      const query = this.input.value.trim();
      const cacheKey = `${this.category}:${normalize(query)}`;
      if (cache.has(cacheKey)) {
        this.render(cache.get(cacheKey), query);
        return;
      }

      this.controller = new AbortController();
      const url = new URL(form.dataset.suggestionsUrl, window.location.origin);
      url.searchParams.set("category", this.category);
      if (query) url.searchParams.set("q", query);

      try {
        const response = await fetch(url, {
          credentials: "same-origin",
          signal: this.controller.signal,
        });
        if (!response.ok) throw new Error("Suggestions could not be loaded");
        const data = await response.json();
        cache.set(cacheKey, data.results);
        if (normalize(this.input.value.trim()) !== normalize(query)) return;
        this.render(data.results, query);
      } catch (error) {
        if (error.name === "AbortError") return;
        this.close();
        this.status.textContent =
          "Impossible de charger les suggestions. Vous pouvez continuer à saisir librement.";
        this.status.hidden = false;
      }
    }

    render(suggestions, query) {
      this.menu.replaceChildren();
      this.suggestions = suggestions;
      this.activeIndex = -1;
      this.status.hidden = true;

      if (suggestions.length === 0) {
        if (query) {
          const empty = document.createElement("div");
          empty.className = "autocomplete-empty";
          empty.textContent = "Aucune suggestion. Votre saisie libre reste possible.";
          this.menu.append(empty);
          this.menu.hidden = false;
          this.input.setAttribute("aria-expanded", "true");
        } else {
          this.close();
        }
        return;
      }

      suggestions.forEach((suggestion, index) => {
        const option = document.createElement("button");
        option.type = "button";
        option.className = "autocomplete-option";
        option.id = `${this.menu.id}-option-${index}`;
        option.setAttribute("role", "option");
        option.setAttribute("aria-selected", "false");
        option.textContent = suggestion.text;
        option.addEventListener("mousedown", (event) => event.preventDefault());
        option.addEventListener("click", () => this.select(suggestion));
        this.menu.append(option);
      });

      this.positionMenu();
      this.menu.hidden = false;
      this.input.setAttribute("aria-expanded", "true");
    }

    setActive(index) {
      this.activeIndex = index;
      const options = this.menu.querySelectorAll("[role=option]");
      options.forEach((option, optionIndex) => {
        const active = optionIndex === index;
        option.setAttribute("aria-selected", String(active));
        if (active) {
          this.input.setAttribute("aria-activedescendant", option.id);
          option.scrollIntoView({ block: "nearest" });
        }
      });
    }

    handleKeydown(event) {
      if (event.key === "Escape") {
        this.close();
        return;
      }
      if (this.menu.hidden || this.suggestions.length === 0) return;
      if (event.key === "ArrowDown") {
        event.preventDefault();
        this.setActive((this.activeIndex + 1) % this.suggestions.length);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        this.setActive(
          (this.activeIndex - 1 + this.suggestions.length) % this.suggestions.length,
        );
      } else if (event.key === "Enter" && this.activeIndex >= 0) {
        event.preventDefault();
        this.select(this.suggestions[this.activeIndex]);
      }
    }

    select(suggestion) {
      this.close();
      this.status.hidden = true;
      const accepted = this.onSelect(suggestion);
      if (accepted === false) return;
      this.input.dispatchEvent(new Event("change", { bubbles: true }));
      void this.recordUsage(suggestion.id);
    }

    async recordUsage(suggestionId) {
      const url = form.dataset.useUrlPattern.replace("/0/", `/${suggestionId}/`);
      try {
        const response = await fetch(url, {
          method: "POST",
          credentials: "same-origin",
          headers: { "X-CSRFToken": csrfToken },
        });
        if (!response.ok) throw new Error("Usage tracking failed");
      } catch {
        this.status.textContent =
          "La sélection est conservée, mais son usage n’a pas pu être enregistré.";
        this.status.hidden = false;
      }
    }
  }

  class TagInput {
    constructor(source) {
      this.source = source;
      this.tags = [];
      this.field = source.closest(".field");
      this.component = document.createElement("div");
      this.component.className = "tag-input";
      this.tagList = document.createElement("div");
      this.tagList.className = "tag-list";
      this.entry = document.createElement("input");
      this.entry.type = "text";
      this.entry.className = "tag-entry";
      this.entry.id = `${source.id || "medical-tags"}-entry`;
      this.entry.autocomplete = "off";
      this.entry.placeholder = source.getAttribute("placeholder") || "Saisir une valeur…";
      this.entry.setAttribute(
        "aria-label",
        source.closest(".field")?.querySelector("label")?.textContent.trim() ||
          "Ajouter une valeur",
      );
      this.field.insertBefore(this.component, source);
      this.component.append(this.tagList, this.entry);
      this.source.hidden = true;
      this.source.required = false;
      this.source.tabIndex = -1;
      this.source.setAttribute("aria-hidden", "true");
      this.tags = source.value
        .split(/\r\n|\r|\n/)
        .map((tag) => tag.trim())
        .filter(Boolean);

      const label = this.field.querySelector(`label[for="${source.id}"]`);
      if (label) label.htmlFor = this.entry.id;

      this.dropdown = new SuggestionDropdown(
        this.entry,
        source.dataset.suggestionCategory,
        this.component,
        (suggestion) => this.add(suggestion.text),
      );
      this.render();

      this.entry.addEventListener("keydown", (event) => {
        if (event.defaultPrevented) return;
        if (event.key === "Enter") {
          event.preventDefault();
          this.add(this.entry.value);
        } else if (
          event.key === "Backspace" &&
          this.entry.value === "" &&
          this.tags.length
        ) {
          this.remove(this.tags.length - 1);
        }
      });
    }

    add(value) {
      const tag = value.trim();
      if (!tag) return false;
      const normalized = normalize(tag);
      if (this.tags.some((item) => normalize(item) === normalized)) {
        this.dropdown.status.textContent = "Cette valeur est déjà ajoutée.";
        this.dropdown.status.hidden = false;
        this.entry.value = "";
        this.render();
        return false;
      }
      this.tags.push(tag);
      this.entry.value = "";
      this.render();
      this.entry.focus();
      return true;
    }

    remove(index) {
      this.tags.splice(index, 1);
      this.render();
      this.entry.focus();
    }

    render() {
      const uniqueTags = [];
      const seen = new Set();
      for (const tag of this.tags) {
        const key = normalize(tag);
        if (key && !seen.has(key)) {
          uniqueTags.push(tag);
          seen.add(key);
        }
      }
      this.tags = uniqueTags;
      this.tagList.replaceChildren();

      this.tags.forEach((tag, index) => {
        const chip = document.createElement("span");
        chip.className = "tag-chip";
        const text = document.createElement("span");
        text.textContent = tag;
        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "tag-remove";
        remove.textContent = "×";
        remove.setAttribute("aria-label", `Supprimer ${tag}`);
        remove.addEventListener("click", () => this.remove(index));
        chip.append(text, remove);
        this.tagList.append(chip);
      });

      this.source.value = this.tags.join("\n");
    }
  }

  document.querySelectorAll("[data-tag-input]").forEach((input) => {
    new TagInput(input);
  });

  document.querySelectorAll("[data-suggestion-category]:not([data-tag-input])").forEach(
    (input) => {
      const field = input.closest(".field");
      input.classList.add("autocomplete-input");
      new SuggestionDropdown(input, input.dataset.suggestionCategory, field, (suggestion) => {
        input.value = suggestion.text;
        return true;
      });
    },
  );
})();
