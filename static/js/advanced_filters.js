document.querySelectorAll("[data-advanced-filter-toggle]").forEach((button) => {
    const panel = document.getElementById(button.getAttribute("aria-controls"));
    if (!panel) {
        return;
    }

    button.addEventListener("click", () => {
        const isOpen = button.getAttribute("aria-expanded") === "true";
        button.setAttribute("aria-expanded", String(!isOpen));
        panel.hidden = isOpen;
        if (!isOpen) {
            const firstInput = panel.querySelector("input, select");
            if (firstInput) {
                firstInput.focus();
            }
        }
    });
});
