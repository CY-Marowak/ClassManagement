import { Fragment, type ReactNode } from "react";
import type { JSONContent } from "@tiptap/react";

export const colors = {
  "#183b36": "深色",
  "#b42318": "紅色",
  "#175cd3": "藍色",
  "#267044": "綠色",
};
export const sizes = { "14px": "小", "16px": "標準", "20px": "大" };
export const emptyDocument: JSONContent = {
  type: "doc",
  content: [{ type: "paragraph" }],
};

export function AnnouncementContent({ body }: { body: JSONContent }) {
  function render(node: JSONContent): ReactNode {
    const children = node.content?.map((child, i) => (
      <Fragment key={i}>{render(child)}</Fragment>
    ));
    switch (node.type) {
      case "doc":
        return children;
      case "paragraph":
        return <p>{children || <br />}</p>;
      case "hardBreak":
        return <br />;
      case "bulletList":
        return <ul>{children}</ul>;
      case "orderedList":
        return <ol start={Number(node.attrs?.start) || 1}>{children}</ol>;
      case "listItem":
        return <li>{children}</li>;
      case "text": {
        let text: ReactNode = node.text;
        for (const mark of [...(node.marks || [])].reverse()) {
          if (mark.type === "bold") text = <strong>{text}</strong>;
          if (mark.type === "italic") text = <em>{text}</em>;
          if (mark.type === "underline") text = <u>{text}</u>;
          if (mark.type === "textStyle") {
            const color = mark.attrs?.color;
            const fontSize = mark.attrs?.fontSize;
            text = (
              <span
                style={{
                  color: Object.hasOwn(colors, color) ? color : undefined,
                  fontSize: Object.hasOwn(sizes, fontSize)
                    ? fontSize
                    : undefined,
                }}
              >
                {text}
              </span>
            );
          }
        }
        return text;
      }
      default:
        return null;
    }
  }
  return <div className="announcement-body">{render(body)}</div>;
}

// Pasted HTML is parsed by the editor's restricted schema. Only palette styles
// survive; event handlers, links, images and unsupported nodes are not stored.
export function normalizePaste(html: string) {
  const doc = new DOMParser().parseFromString(html, "text/html");
  const rgb: Record<string, string> = {
    "rgb(24, 59, 54)": "#183b36",
    "rgb(180, 35, 24)": "#b42318",
    "rgb(23, 92, 211)": "#175cd3",
    "rgb(38, 112, 68)": "#267044",
  };
  for (const el of doc.body.querySelectorAll<HTMLElement>("*")) {
    const color = rgb[el.style.color] || el.style.color;
    const size = el.style.fontSize;
    const bold =
      el.style.fontWeight === "bold" || Number(el.style.fontWeight) >= 600;
    const italic = el.style.fontStyle === "italic";
    const underline = el.style.textDecoration.includes("underline");
    const start = Number(el.getAttribute("start"));
    for (const attr of Array.from(el.attributes)) el.removeAttribute(attr.name);
    if (Object.hasOwn(colors, color)) el.style.color = color;
    if (Object.hasOwn(sizes, size)) el.style.fontSize = size;
    if (bold) el.style.fontWeight = "bold";
    if (italic) el.style.fontStyle = "italic";
    if (underline) el.style.textDecoration = "underline";
    if (
      el.tagName === "OL" &&
      Number.isInteger(start) &&
      start >= 1 &&
      start <= 9999
    )
      el.setAttribute("start", String(start));
  }
  return doc.body.innerHTML;
}
