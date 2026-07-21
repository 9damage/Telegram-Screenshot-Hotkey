(() => {
    const duration = 10000;
    const scheduled = new WeakSet();

    function schedule(notification) {
        if (!notification.classList?.contains("flash") || scheduled.has(notification)) return;
        scheduled.add(notification);

        const timer = document.createElement("span");
        timer.className = "toast-timer";
        timer.setAttribute("aria-hidden", "true");
        timer.innerHTML = `
            <svg viewBox="0 0 24 24">
                <circle class="toast-timer-track" cx="12" cy="12" r="9" pathLength="100"></circle>
                <circle class="toast-timer-progress" cx="12" cy="12" r="9" pathLength="100"></circle>
            </svg>`;
        notification.append(timer);

        window.setTimeout(() => notification.classList.add("is-leaving"), duration - 300);
        window.setTimeout(() => notification.remove(), duration);
    }

    function inspect(node) {
        if (!(node instanceof Element)) return;
        schedule(node);
        node.querySelectorAll(".flash").forEach(schedule);
    }

    document.querySelectorAll(".flash").forEach(schedule);
    new MutationObserver((mutations) => {
        mutations.forEach((mutation) => mutation.addedNodes.forEach(inspect));
    }).observe(document.body, { childList: true, subtree: true });
})();
