function setupVocabularyOwnershipFilter() {
    const toggle = document.querySelector("[data-filter-toggle]");
    const countElement = document.querySelector("[data-filter-count]");
    const rows = Array.from(document.querySelectorAll("[data-owned]"));
    const emptyMessage = document.querySelector("[data-filter-empty]");

    if (!toggle || !countElement || rows.length === 0) {
        return;
    }

    const buttons = Array.from(toggle.querySelectorAll("[data-filter-value]"));
    const singular = countElement.dataset.countSingular || "entry";
    const plural = countElement.dataset.countPlural || "entries";

    function updateCount(visibleCount) {
        const label = visibleCount === 1 ? singular : plural;
        countElement.textContent = `${visibleCount} ${label}`;
    }

    function applyFilter(filterValue) {
        let visibleCount = 0;

        rows.forEach((row) => {
            const shouldShow = filterValue === "all" || row.dataset.owned === "true";
            row.hidden = !shouldShow;
            if (!shouldShow) {
                row.querySelectorAll('input[type="checkbox"]:checked').forEach((checkbox) => {
                    checkbox.checked = false;
                    checkbox.dispatchEvent(new Event("change", {bubbles: true}));
                });
            }
            if (shouldShow) {
                visibleCount += 1;
            }
        });

        buttons.forEach((button) => {
            const isActive = button.dataset.filterValue === filterValue;
            button.classList.toggle("is-active", isActive);
            button.setAttribute("aria-pressed", isActive ? "true" : "false");
        });

        updateCount(visibleCount);
        if (emptyMessage) {
            emptyMessage.hidden = visibleCount !== 0 || filterValue !== "own";
        }
    }

    buttons.forEach((button) => {
        button.addEventListener("click", () => {
            applyFilter(button.dataset.filterValue);
        });
    });

    applyFilter("all");
}

setupVocabularyOwnershipFilter();
