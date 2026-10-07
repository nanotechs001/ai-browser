// Pictures and files pasted (Command-V, Ctrl+V) or dropped into a box where the user writes to Claude (the user's look,
// 2026-10-07): they go to `onFiles(files)`, which attaches them as Attach does (uploads.js), or says where pictures
// go. Only files become chips: pasted or dropped text is left to the browser, which puts it in the box as text. A
// paste can hold both: cells copied from a spreadsheet come with a picture of them that the browser names image.png
// (they are text, and no chip), and a file copied in the Finder comes with its name (the file is attached too).
"use strict";

export const PICTURES_NOTE = "Pictures go with Build a Mission or an agent's chat"; // a box that takes no files

export function filesOf(transfer) { // the files a paste or a drop carries: a copied screenshot is one (image.png)
  const files = [...(transfer?.files || [])];
  if (files.length) return files;
  return [...(transfer?.items || [])].filter((item) => item.kind === "file").map((item) => item.getAsFile())
    .filter(Boolean);
}

const GENERIC = /^image\.[a-z0-9]+$/i; // the name a browser gives a picture with no name of its own

function carriesFiles(event) {
  return [...(event.dataTransfer?.types || [])].includes("Files");
}

// Pastes into `box` and drops on `area` (the box itself, or the part of the page around it).
export function takeFiles(box, onFiles, { area = box } = {}) {
  box.addEventListener("paste", (event) => {
    const files = filesOf(event.clipboardData);
    if (!files.length) return; // text: pasted as text
    if (!event.clipboardData.types.includes("text/plain")) event.preventDefault(); // nothing else to paste
    else if (files.every((file) => file.type.startsWith("image/") && GENERIC.test(file.name))) return; // cells
    onFiles(files);
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
    onFiles(files);
  });
}
