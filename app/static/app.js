const textInput = document.getElementById("textInput");
const languageInput = document.getElementById("languageInput");
const voiceInput = document.getElementById("voiceInput");
const maxChunkInput = document.getElementById("maxChunkInput");
const fileInput = document.getElementById("fileInput");
const generateBtn = document.getElementById("generateBtn");
const refreshBtn = document.getElementById("refreshBtn");
const statusBox = document.getElementById("statusBox");
const historyList = document.getElementById("historyList");

function formatBytes(bytes) {
    if (!bytes) return "0 B";

    const units = ["B", "KB", "MB", "GB"];
    let size = bytes;
    let unitIndex = 0;

    while (size >= 1024 && unitIndex < units.length - 1) {
        size = size / 1024;
        unitIndex++;
    }

    return `${size.toFixed(unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}

function setStatus(message, isError = false) {
    statusBox.textContent = message;
    statusBox.style.color = isError ? "#fca5a5" : "#93c5fd";
}

async function loadHistory() {
    historyList.innerHTML = `<div class="empty">Loading history...</div>`;

    try {
        const response = await fetch("/api/history");

        if (!response.ok) {
            throw new Error(`Failed to load history. HTTP ${response.status}`);
        }

        const data = await response.json();
        const items = data.items || [];

        if (items.length === 0) {
            historyList.innerHTML = `<div class="empty">No audio files generated yet.</div>`;
            return;
        }

        historyList.innerHTML = items
            .map((item) => {
                return `
                    <div class="historyItem">
                        <p class="historyTitle">${item.filename}</p>
                        <p class="historyMeta">
                        ${item.created} · ${formatBytes(item.size_bytes)}
                        </p>
                        <audio controls src="${item.url}"></audio>

                        <div class="historyActions">
                        <a class="downloadLink" href="${item.url}" download="${item.filename}">
                            Download
                        </a>

                        <button class="deleteBtn" onclick="deleteHistoryItem('${item.filename}')">
                            Delete
                        </button>
                        </div>
                    </div>
                    `;
            })
            .join("");
    } catch (error) {
        historyList.innerHTML = `<div class="empty">Could not load history.</div>`;
        setStatus(error.message, true);
    }
}

async function deleteHistoryItem(filename) {
    const confirmed = confirm(`Delete ${filename}?`);

    if (!confirmed) {
        return;
    }

    try {
        const response = await fetch(`/api/history/${encodeURIComponent(filename)}`, {
            method: "DELETE",
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || `HTTP ${response.status}`);
        }

        setStatus(`Deleted ${filename}`);
        await loadHistory();
    } catch (error) {
        setStatus(error.message || String(error), true);
    }
}

async function generateAudio() {
    const formData = new FormData();

    formData.append("text", textInput.value || "");
    formData.append("language", languageInput.value || "English");
    formData.append("voice_description", voiceInput.value || "");
    formData.append("max_chars_per_chunk", maxChunkInput.value || "1200");

    for (const file of fileInput.files) {
        formData.append("files", file);
    }

    generateBtn.disabled = true;
    setStatus("Generating audio...");

    try {
        const response = await fetch("/api/generate", {
            method: "POST",
            body: formData,
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || `HTTP ${response.status}`);
        }

        setStatus(
            `Generated ${data.count} audio file(s).\n\n` +
            data.items
                .map((x) => `${x.filename} - ${x.characters} chars - ${x.chunks} chunk(s)`)
                .join("\n")
        );

        await loadHistory();
    } catch (error) {
        setStatus(error.message || String(error), true);
    } finally {
        generateBtn.disabled = false;
    }
}

generateBtn.addEventListener("click", generateAudio);
refreshBtn.addEventListener("click", loadHistory);

loadHistory();