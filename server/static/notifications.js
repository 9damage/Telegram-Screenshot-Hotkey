(() => {
    const duration = 10000;
    const scheduled = new WeakSet();
    const positions = new WeakMap();
    let animationFrame = 0;

    function animateStack() {
        animationFrame = 0;
        document.querySelectorAll(".toast-container .flash").forEach((notification) => {
            const nextTop = notification.getBoundingClientRect().top;
            const previousTop = positions.get(notification);

            if (previousTop !== undefined && previousTop !== nextTop) {
                notification.animate(
                    [
                        { transform: `translateY(${previousTop - nextTop}px)` },
                        { transform: "translateY(0)" },
                    ],
                    { duration: 280, easing: "cubic-bezier(.2,.8,.2,1)" },
                );
            }

            positions.set(notification, nextTop);
        });
    }

    function queueStackAnimation() {
        if (animationFrame) return;
        animationFrame = window.requestAnimationFrame(animateStack);
    }

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
    animateStack();
    new MutationObserver((mutations) => {
        mutations.forEach((mutation) => mutation.addedNodes.forEach(inspect));
        queueStackAnimation();
    }).observe(document.body, { childList: true, subtree: true });
})();
