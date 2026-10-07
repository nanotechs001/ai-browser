// Pictures and files pasted (Command-V, Ctrl+V) or dropped into a box where the user writes to Claude (the user's look,
// 2026-10-07): they go to `onFiles(files, {text})`, which attaches them as Attach does (uploads.js), or says where
// pictures go. Only files become chips: pasted or dropped text is left to the browser, which puts it in the box as
// text. A paste can hold both (cells copied from a spreadsheet come with a picture of them; a file copied in the
// Finder with its name): the text goes in the box, the files to `onFiles` with text: true.
"use strict";

export const PICTURES_NOTE = "Pictures go with Build a Mission or an agent's chat"; // a box that takes no files

export function filesOf(transfer) { // the files a paste or a drop carries: a copied screenshot is one (image.png)
  const files = [...(transfer?.files || [])];
  if (files.length) return files;
  return [...(transfer?.items || [])].filter((item) => item.kind === "file").map((item) => item.getAsFile())
    .filter(Boolean);
}

function carriesFiles(event) {
  return [...(event.dataTransfer?.types || [])].includes("Files");
}

// Pastes into `box` and drops on `area` (the box itself, or the part of the page around it).
export function takeFiles(box, onFiles, { area = box } = {}) {
  box.addEventListener("paste", (event) => {
    const files = filesOf(event.clipboardData);
    if (!files.length) return; // text: pasted as text
    const text = event.clipboardData.types.includes("text/plain");
    if (!text) event.preventDefault(); // nothing else to paste
    onFiles(files, { text });
  });
  area.addEventListener("dragover", (event) => {
    if (!carriesFiles(event)) return; // dragged text: the browser's
    event.preventDefault(); // a drop here, never the browser opening the file
    event.dataTransfer.dropEffect = "copy";
    area.classList.add("dropping");
  });
  area.addEventListener("dragleave", (event) => {
    if (!area.contains(event.relatedTarget)) area.classList.remove("dropping");
  });
  area.addEventListener("drop", (event) => {
    area.classList.remove("dropping");
    const files = filesOf(event.dataTransfer);
    if (!files.length) return;
    event.preventDefault();
    onFiles(files, { text: false });
  });
}
