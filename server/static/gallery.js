(() => {
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || "";
    const grid = document.querySelector("#gallery-grid");
    const emptyState = document.querySelector("#empty-state");
    const selectAll = document.querySelector("#select-all");
    const deleteSelected = document.querySelector("#delete-selected");
    const selectedCount = document.querySelector("#selected-count");
    const bulkForm = document.querySelector("#bulk-form");
    const viewer = document.querySelector("#viewer-dialog");
    const viewerImage = document.querySelector("#viewer-image");
    const viewerTitle = document.querySelector("#viewer-title");
    const clearDialog = document.querySelector("#clear-dialog");
    const liveIndicator = document.querySelector("#live-indicator");
    const stopClient = document.querySelector("#stop-client");
    const stopClientForm = document.querySelector("#stop-client-form");
    const liveNotifications = document.querySelector("#live-notifications");
    const currentPage = Number(document.body.dataset.page || "1");
    const closeIconUrl = document.body.dataset.closeIconUrl || "/static/close-icon.svg";
    let lastClientEventId = Number(document.body.dataset.clientEventId || "0");
    let notificationTimer = null;

    function showNotification(message, category = "success") {
        if (!message || !liveNotifications) return;
        const notification = document.createElement("div");
        notification.className = `flash flash-${category}`;
        notification.setAttribute("role", "status");
        notification.textContent = message;
        liveNotifications.replaceChildren(notification);
        window.clearTimeout(notificationTimer);
        notificationTimer = window.setTimeout(() => {
            notification.remove();
            notificationTimer = null;
        }, 10000);
    }

    function handleClientEvent(event) {
        const eventId = Number(event?.id || 0);
        if (eventId <= lastClientEventId) return;
        lastClientEventId = eventId;
        if (event.kind === "stopped") showNotification(event.message);
    }

    function checkboxes() {
        return [...document.querySelectorAll(".screenshot-checkbox")];
    }

    function updateSelection() {
        const boxes = checkboxes();
        const selected = boxes.filter((box) => box.checked).length;
        deleteSelected.disabled = selected === 0;
        selectedCount.textContent = selected ? `(${selected})` : "";
        selectAll.checked = boxes.length > 0 && selected === boxes.length;
        selectAll.indeterminate = selected > 0 && selected < boxes.length;
    }

    function updateEmptyState() {
        const empty = !grid.querySelector(".screenshot-card");
        emptyState.hidden = !empty;
        document.querySelector("#open-clear-dialog").disabled = empty;
    }

    async function openViewer(button) {
        viewerImage.src = button.dataset.viewImage;
        viewerTitle.textContent = button.dataset.viewTitle;
        viewer.showModal();
        const card = button.closest(".screenshot-card");
        if (card?.classList.contains("is-unviewed")) {
            const response = await fetch(button.dataset.markViewedUrl, {
                method: "POST",
                headers: { "X-CSRF-Token": csrfToken },
            });
            if (response.ok) {
                card.classList.remove("is-unviewed");
                card.querySelector(".new-badge")?.remove();
                const counter = document.querySelector("#unviewed-count");
                counter.textContent = Math.max(Number(counter.textContent || "0") - 1, 0);
            }
        }
    }

    async function deleteOne(button) {
        if (!window.confirm("Удалить этот скриншот? Действие нельзя отменить.")) return;
        button.disabled = true;
        const body = new URLSearchParams({ csrf_token: csrfToken });
        const response = await fetch(button.dataset.deleteUrl, {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body,
        });
        if (!response.ok) {
            button.disabled = false;
            window.alert("Не удалось удалить скриншот.");
            return;
        }
        button.closest(".screenshot-card")?.remove();
        updateSelection();
        updateEmptyState();
        await refreshGallery();
    }

    function bindCard(card) {
        card.querySelector(".screenshot-checkbox")?.addEventListener("change", updateSelection);
        card.querySelector(".image-button")?.addEventListener("click", (event) => openViewer(event.currentTarget));
        card.querySelector(".delete-one")?.addEventListener("click", (event) => deleteOne(event.currentTarget));
    }

    function createCard(item) {
        const card = document.createElement("article");
        card.className = `screenshot-card${item.viewed ? "" : " is-unviewed"}`;
        card.dataset.screenshotId = item.id;

        if (!item.viewed) {
            const badge = document.createElement("span");
            badge.className = "new-badge";
            badge.textContent = "Новый";
            card.append(badge);
        }

        const selectLabel = document.createElement("label");
        selectLabel.className = "card-select";
        selectLabel.setAttribute("aria-label", "Выбрать скриншот");
        const checkbox = document.createElement("input");
        checkbox.className = "screenshot-checkbox";
        checkbox.type = "checkbox";
        checkbox.name = "selected";
        checkbox.value = item.id;
        selectLabel.append(checkbox);

        const imageButton = document.createElement("button");
        imageButton.className = "image-button";
        imageButton.type = "button";
        imageButton.dataset.viewImage = item.image_url;
        imageButton.dataset.viewTitle = item.created_label;
        imageButton.dataset.markViewedUrl = item.mark_viewed_url;
        const image = document.createElement("img");
        image.src = item.image_url;
        image.alt = `Скриншот от ${item.created_label}`;
        image.loading = "lazy";
        imageButton.append(image);

        const meta = document.createElement("div");
        meta.className = "card-meta";
        const details = document.createElement("div");
        const time = document.createElement("time");
        time.textContent = item.created_label;
        const size = document.createElement("span");
        size.textContent = item.size_label;
        details.append(time, size);
        const remove = document.createElement("button");
        remove.className = "icon-button delete-one";
        remove.type = "button";
        remove.dataset.deleteUrl = item.delete_url;
        remove.setAttribute("aria-label", "Удалить скриншот");
        remove.title = "Удалить";
        const removeIcon = document.createElement("img");
        removeIcon.className = "close-icon";
        removeIcon.src = closeIconUrl;
        removeIcon.alt = "";
        removeIcon.setAttribute("aria-hidden", "true");
        remove.append(removeIcon);
        meta.append(details, remove);

        card.append(selectLabel, imageButton, meta);
        bindCard(card);
        return card;
    }

    async function refreshGallery() {
        try {
            const response = await fetch("/api/gallery-state", {
                headers: { "Accept": "application/json" },
                cache: "no-store",
            });
            if (!response.ok) throw new Error("refresh_failed");
            const state = await response.json();

            document.querySelector("#total-count").textContent = state.total;
            document.querySelector("#storage-size").textContent = state.size_label;
            document.querySelector("#unviewed-count").textContent = state.unviewed;
            document.querySelector("#queue-count").textContent = state.queue_count;
            const clientStatus = document.querySelector("#client-status");
            clientStatus.textContent = state.client_active ? "Активен" : "Неактивен";
            clientStatus.className = state.client_active ? "status-online" : "status-offline";
            if (stopClient) stopClient.disabled = !state.client_active || state.stop_pending;
            handleClientEvent(state.client_event);

            if (currentPage === 1) {
                const incomingIds = new Set(state.screenshots.map((item) => item.id));
                grid.querySelectorAll(".screenshot-card").forEach((card) => {
                    if (!incomingIds.has(card.dataset.screenshotId)) card.remove();
                });

                [...state.screenshots].reverse().forEach((item) => {
                    if (!grid.querySelector(`[data-screenshot-id="${CSS.escape(item.id)}"]`)) {
                        grid.prepend(createCard(item));
                    }
                });
            }

            liveIndicator?.classList.remove("is-paused");
            updateSelection();
            updateEmptyState();
        } catch (_error) {
            liveIndicator?.classList.add("is-paused");
        }
    }

    document.querySelectorAll(".screenshot-card").forEach(bindCard);
    selectAll?.addEventListener("change", () => {
        checkboxes().forEach((box) => { box.checked = selectAll.checked; });
        updateSelection();
    });
    bulkForm?.addEventListener("submit", (event) => {
        const count = checkboxes().filter((box) => box.checked).length;
        if (!count || !window.confirm(`Удалить выбранные скриншоты (${count})?`)) event.preventDefault();
    });
    document.querySelector("#close-viewer")?.addEventListener("click", () => viewer.close());
    viewer?.addEventListener("click", (event) => { if (event.target === viewer) viewer.close(); });
    document.querySelector("#open-clear-dialog")?.addEventListener("click", () => clearDialog.showModal());
    document.querySelector("#cancel-clear")?.addEventListener("click", () => clearDialog.close());
    stopClientForm?.addEventListener("submit", async (event) => {
        event.preventDefault();
        if (!window.confirm("Завершить процесс на подключённом устройстве?")) {
            return;
        }

        stopClient.disabled = true;
        try {
            const response = await fetch(stopClientForm.action, {
                method: "POST",
                headers: { "Accept": "application/json" },
                body: new FormData(stopClientForm),
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.message || "Не удалось отправить команду.");
            lastClientEventId = Math.max(lastClientEventId, Number(result.client_event_id || 0));
            showNotification(result.message);
        } catch (error) {
            showNotification(error.message || "Не удалось отправить команду.", "error");
            stopClient.disabled = false;
        }
    });

    updateSelection();
    updateEmptyState();
    window.setInterval(() => { if (!document.hidden) refreshGallery(); }, 4000);
})();
