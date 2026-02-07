const REPORT_PATH = "/api/report";
const UPLOAD_PATH = "/api/upload";
const IMAGE_ROOT = "/out/redacted_images";

const gallery = document.getElementById("gallery");
const detectionsBody = document.getElementById("detections");
const summary = document.getElementById("summary");
const refreshButton = document.getElementById("refresh");
const uploadForm = document.getElementById("upload-form");
const fileInput = document.getElementById("file-input");
const uploadStatus = document.getElementById("upload-status");

const formatPage = (page) => String(page).padStart(3, "0");

const buildImagePath = (filePath, page) => {
  const stem = filePath.split("/").pop().split(".").slice(0, -1).join(".");
  return `${IMAGE_ROOT}/${stem}_${formatPage(page)}.png`;
};

const renderGallery = (pages) => {
  gallery.innerHTML = "";
  if (!pages.length) {
    gallery.innerHTML = "<p class=\"empty\">No redacted pages found.</p>";
    return;
  }

  pages.forEach((page) => {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <img src="${page.imagePath}" alt="${page.label}" loading="lazy" />
      <h3>${page.label}</h3>
    `;
    gallery.appendChild(card);
  });
};

const renderSummary = (detections) => {
  summary.innerHTML = "";
  if (!detections.length) {
    return;
  }
  const counts = detections.reduce((acc, detection) => {
    acc[detection.type] = (acc[detection.type] || 0) + 1;
    return acc;
  }, {});

  Object.entries(counts).forEach(([type, count]) => {
    const pill = document.createElement("div");
    pill.className = "pill";
    pill.textContent = `${type}: ${count}`;
    summary.appendChild(pill);
  });
};

const renderDetections = (entries) => {
  detectionsBody.innerHTML = "";
  if (!entries.length) {
    detectionsBody.innerHTML =
      "<tr><td colspan=\"6\" class=\"empty\">No detections in report.</td></tr>";
    return;
  }

  entries.forEach((entry) => {
    if (!entry.detections.length) {
      return;
    }
    entry.detections.forEach((detection) => {
      const row = document.createElement("tr");
      row.innerHTML = `
        <td>${entry.file}</td>
        <td>${entry.page}</td>
        <td>${entry.language}</td>
        <td>${detection.type}</td>
        <td>${detection.text_sample}</td>
        <td>${detection.confidence.toFixed(2)}</td>
      `;
      detectionsBody.appendChild(row);
    });
  });

  if (!detectionsBody.children.length) {
    detectionsBody.innerHTML =
      "<tr><td colspan=\"6\" class=\"empty\">No detections in report.</td></tr>";
  }
};

const loadReport = async () => {
  gallery.innerHTML = "<p class=\"empty\">Loading redacted pages…</p>";
  detectionsBody.innerHTML =
    "<tr><td colspan=\"6\" class=\"empty\">Loading detections…</td></tr>";
  summary.innerHTML = "";

  try {
    const response = await fetch(REPORT_PATH, { cache: "no-store" });
    if (!response.ok) {
      throw new Error("Report not found");
    }
    const entries = await response.json();

    const pages = entries.map((entry) => ({
      imagePath: entry.image_path || buildImagePath(entry.file, entry.page),
      label: `${entry.file.split("/").pop()} · Page ${entry.page}`,
    }));

    renderGallery(pages);
    renderDetections(entries);

    const allDetections = entries.flatMap((entry) => entry.detections);
    renderSummary(allDetections);
  } catch (error) {
    gallery.innerHTML =
      "<p class=\"empty\">Unable to load report. Upload invoices to start.</p>";
    detectionsBody.innerHTML =
      "<tr><td colspan=\"6\" class=\"empty\">Report not available.</td></tr>";
  }
};

uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!fileInput.files.length) {
    uploadStatus.textContent = "Please select a file to upload.";
    return;
  }
  const file = fileInput.files[0];
  const formData = new FormData();
  formData.append("file", file);

  uploadStatus.textContent = "Uploading and processing…";
  try {
    const response = await fetch(UPLOAD_PATH, {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      const data = await response.json();
      throw new Error(data.error || "Upload failed");
    }
    const data = await response.json();
    uploadStatus.textContent = `Processed ${data.pages} page(s).`;
    fileInput.value = "";
    await loadReport();
  } catch (error) {
    uploadStatus.textContent = `Error: ${error.message}`;
  }
});

refreshButton.addEventListener("click", loadReport);

loadReport();
