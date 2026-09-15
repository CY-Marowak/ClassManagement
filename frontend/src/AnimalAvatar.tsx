import type { Student } from "./api";

export const animalNames = { cat: "貓", dog: "狗", rabbit: "兔" };

// Original geometric artwork made for CM; no external icon paths or image assets.
export function AnimalAvatar({ animal }: { animal: Student["avatar"] }) {
  return (
    <svg
      className="animal-avatar"
      viewBox="0 0 120 120"
      role="img"
      aria-label={`${animalNames[animal]}角色`}
    >
      <circle cx="60" cy="60" r="57" fill="#edf2df" />
      <g
        stroke="#405849"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {animal === "cat" && (
          <>
            <path
              d="M29 57 L27 23 L49 39 M71 39 L93 23 L91 57"
              fill="#e9bd78"
            />
            <path
              d="M33 41 L32 32 L41 39 M79 39 L88 32 L87 41"
              fill="#df9b89"
            />
          </>
        )}
        {animal === "rabbit" && (
          <>
            <ellipse cx="44" cy="31" rx="11" ry="25" fill="#fffaf0" />
            <ellipse cx="76" cy="31" rx="11" ry="25" fill="#fffaf0" />
            <path d="M44 17 V38 M76 17 V38" stroke="#e1aaa2" strokeWidth="6" />
          </>
        )}
        <ellipse
          cx="60"
          cy="65"
          rx="35"
          ry="31"
          fill={
            animal === "cat"
              ? "#edc889"
              : animal === "dog"
                ? "#d4b392"
                : "#fffaf0"
          }
        />
        {animal === "dog" && (
          <>
            <ellipse
              cx="28"
              cy="54"
              rx="12"
              ry="23"
              fill="#a98267"
              transform="rotate(16 28 54)"
            />
            <ellipse
              cx="92"
              cy="54"
              rx="12"
              ry="23"
              fill="#a98267"
              transform="rotate(-16 92 54)"
            />
          </>
        )}
        <path d="M45 61 v3 M75 61 v3" strokeWidth="5" />
        <path d="M56 73 L60 76 L64 73 Z" fill="#405849" />
        <path d="M60 77 Q54 86 49 79 M60 77 Q66 86 71 79" fill="none" />
        {animal === "cat" && (
          <path d="M23 69 L39 72 M23 79 L39 77 M81 72 L97 69 M81 77 L97 79" />
        )}
      </g>
    </svg>
  );
}
