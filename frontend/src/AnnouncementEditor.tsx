import { useEffect } from "react";
import {
  EditorContent,
  useEditor,
  useEditorState,
  type JSONContent,
} from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { TextStyle, Color, FontSize } from "@tiptap/extension-text-style";
import { colors, sizes, normalizePaste } from "./AnnouncementContent";

export function AnnouncementEditor({
  body,
  disabled,
  onChange,
}: {
  body: JSONContent;
  disabled: boolean;
  onChange: (body: JSONContent) => void;
}) {
  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: false,
        blockquote: false,
        code: false,
        codeBlock: false,
        horizontalRule: false,
        strike: false,
        link: false,
      }),
      TextStyle,
      Color,
      FontSize,
    ],
    content: body,
    editorProps: {
      attributes: {
        role: "textbox",
        "aria-label": "公告內文",
        "aria-multiline": "true",
      },
      transformPastedHTML: normalizePaste,
    },
    onUpdate: ({ editor }) => onChange(editor.getJSON()),
  });
  const state = useEditorState({
    editor,
    selector: ({ editor }) => ({
      bold: editor?.isActive("bold"),
      italic: editor?.isActive("italic"),
      underline: editor?.isActive("underline"),
      bullet: editor?.isActive("bulletList"),
      ordered: editor?.isActive("orderedList"),
      color: editor?.getAttributes("textStyle").color || "#183b36",
      size: editor?.getAttributes("textStyle").fontSize || "16px",
    }),
  });
  useEffect(() => {
    editor?.setEditable(!disabled);
  }, [editor, disabled]);
  if (!editor) return null;
  return (
    <div className="announcement-editor">
      <fieldset
        disabled={disabled}
        className="rich-toolbar"
        aria-label="文字格式"
      >
        <button
          type="button"
          aria-pressed={state?.bold}
          onClick={() => editor.chain().focus().toggleBold().run()}
        >
          粗體
        </button>
        <button
          type="button"
          aria-pressed={state?.italic}
          onClick={() => editor.chain().focus().toggleItalic().run()}
        >
          斜體
        </button>
        <button
          type="button"
          aria-pressed={state?.underline}
          onClick={() => editor.chain().focus().toggleUnderline().run()}
        >
          底線
        </button>
        <label>
          字體大小
          <select
            value={state?.size}
            onChange={(e) =>
              editor.chain().focus().setFontSize(e.target.value).run()
            }
          >
            {Object.entries(sizes).map(([v, label]) => (
              <option key={v} value={v}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          文字顏色
          <select
            value={state?.color}
            onChange={(e) =>
              editor.chain().focus().setColor(e.target.value).run()
            }
          >
            {Object.entries(colors).map(([v, label]) => (
              <option key={v} value={v}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          aria-pressed={state?.bullet}
          onClick={() => editor.chain().focus().toggleBulletList().run()}
        >
          項目符號
        </button>
        <button
          type="button"
          aria-pressed={state?.ordered}
          onClick={() => editor.chain().focus().toggleOrderedList().run()}
        >
          編號清單
        </button>
        <button
          type="button"
          onClick={() =>
            editor.chain().focus().unsetAllMarks().clearNodes().run()
          }
        >
          清除格式
        </button>
      </fieldset>
      <EditorContent editor={editor} />
      <p className="muted small">
        內文 1～5000 字；可貼上文字，支援的格式會保留。
      </p>
    </div>
  );
}
