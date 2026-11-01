import { studentRoleNames, type StudentRole } from "./studentRoles";

const fur: Record<StudentRole, string> = {
  rat: "#b9c4c3",
  cow: "#fff5df",
  tiger: "#e9b46c",
  rabbit: "#fff5df",
  dragon: "#a9c99d",
  snake: "#b8ce8f",
  horse: "#c99a78",
  goat: "#f5ead3",
  monkey: "#b58a68",
  rooster: "#fff1cb",
  dog: "#d4b392",
  pig: "#edb7aa",
  cat: "#edc889",
};

// Original CM SVGs, extending the approved cat/cow samples. Static student art only.
export function StudentAvatar({ animal }: { animal: StudentRole }) {
  return (
    <svg
      className="animal-avatar"
      viewBox="0 0 120 140"
      role="img"
      aria-label={`${studentRoleNames[animal]}角色`}
    >
      <circle cx="60" cy="70" r="57" fill="#e8eddb" />
      <g
        stroke="#405849"
        strokeWidth="2.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {animal === "cat" && (
          <>
            <path
              d="M28 55 L27 21 Q40 24 49 39 M71 39 Q80 24 93 21 L92 55"
              fill={fur.cat}
            />
            <path
              d="M33 42 L33 30 L43 39 M77 39 L87 30 L87 42"
              fill="#dda28d"
            />
          </>
        )}
        {animal === "cow" && (
          <>
            <path
              d="M39 41 Q14 24 19 48 Q26 57 40 51 M81 41 Q106 24 101 48 Q94 57 80 51"
              fill="#ac8261"
            />
            <path
              d="M39 36 Q29 21 41 21 L48 37 M72 37 L79 21 Q91 21 81 36"
              fill="#ebd19b"
            />
          </>
        )}
        {(animal === "rat" || animal === "tiger" || animal === "monkey") && (
          <>
            <circle
              cx="29"
              cy="42"
              r={animal === "rat" ? 19 : 14}
              fill={fur[animal]}
            />
            <circle
              cx="91"
              cy="42"
              r={animal === "rat" ? 19 : 14}
              fill={fur[animal]}
            />
            <circle cx="29" cy="42" r="8" fill="#e9b7a1" />
            <circle cx="91" cy="42" r="8" fill="#e9b7a1" />
          </>
        )}
        {animal === "rabbit" && (
          <>
            <ellipse cx="44" cy="34" rx="10" ry="27" fill={fur.rabbit} />
            <ellipse cx="76" cy="34" rx="10" ry="27" fill={fur.rabbit} />
            <path d="M44 17 V39 M76 17 V39" stroke="#e1aaa2" strokeWidth="5" />
          </>
        )}
        {animal === "dragon" && (
          <>
            <path
              d="M38 44 L28 20 M31 28 L20 24 M82 44 L92 20 M89 28 L100 24"
              stroke="#b18b60"
              strokeWidth="6"
            />
            <path
              d="M27 56 L14 46 L19 69 L30 73 M93 56 L106 46 L101 69 L90 73"
              fill="#7cae92"
            />
          </>
        )}
        {animal === "horse" && (
          <>
            <path
              d="M34 50 Q24 12 40 23 L49 42 M71 42 L80 23 Q96 12 86 50"
              fill={fur.horse}
            />
            <path d="M37 29 L41 42 M83 29 L79 42" stroke="#e5b8a0" />
          </>
        )}
        {animal === "goat" && (
          <>
            <path
              d="M38 43 Q15 20 31 18 Q41 18 44 43 M76 43 Q79 18 89 18 Q105 20 82 43"
              fill="#c7ab7d"
            />
            <path
              d="M35 55 Q11 41 19 63 L35 68 M85 55 Q109 41 101 63 L85 68"
              fill="#e9d4b4"
            />
          </>
        )}
        {animal === "rooster" && (
          <path
            d="M46 43 Q29 20 44 21 Q40 3 53 13 Q66 -1 68 18 Q86 10 78 33 L73 45"
            fill="#db8d78"
          />
        )}
        {animal === "pig" && (
          <path
            d="M35 53 Q7 17 25 24 L48 40 M72 40 L95 24 Q113 17 85 53"
            fill="#df9e93"
          />
        )}
        {animal === "snake" && (
          <ellipse cx="60" cy="99" rx="29" ry="13" fill={fur.snake} />
        )}
        <ellipse
          cx="60"
          cy={animal === "horse" ? 72 : 64}
          rx={animal === "horse" ? 29 : 35}
          ry={animal === "horse" ? 38 : 30}
          fill={fur[animal]}
        />
        {animal === "dog" && (
          <>
            <ellipse
              cx="29"
              cy="57"
              rx="12"
              ry="24"
              fill="#a98267"
              transform="rotate(16 29 57)"
            />
            <ellipse
              cx="91"
              cy="57"
              rx="12"
              ry="24"
              fill="#a98267"
              transform="rotate(-16 91 57)"
            />
          </>
        )}
        {animal === "monkey" && (
          <path
            d="M60 49 C35 32 26 59 38 70 C25 93 95 93 82 70 C94 59 85 32 60 49"
            fill="#f3d7af"
            stroke="none"
          />
        )}
        {animal === "goat" && (
          <>
            <path
              d="M32 46 Q24 31 40 31 Q45 20 55 29 Q65 18 74 29 Q92 25 88 43 Q72 54 60 43 Q48 54 32 46"
              fill="#fff8e7"
            />
            <path d="M51 91 L60 105 L69 91" fill="#fff8e7" />
          </>
        )}
        {animal === "horse" && (
          <path
            d="M37 45 Q37 26 58 29 Q82 26 85 50 L72 45 L67 57 L58 44 L49 53 L49 40 Z"
            fill="#86674f"
          />
        )}
        {animal === "cow" && (
          <path
            d="M36 43 Q55 30 53 58 Q44 66 32 56"
            fill="#ac8261"
            stroke="none"
          />
        )}
        {animal === "cat" && (
          <>
            <path d="M52 37 L55 47 M65 47 L68 37" stroke="#c59759" />
            <path
              d="M22 70 L38 72 M23 79 L38 77 M82 72 L98 70 M82 77 L97 79"
              strokeWidth="2"
            />
          </>
        )}
        {animal === "tiger" && (
          <path
            d="M60 36 V48 M50 39 L53 47 M70 39 L67 47 M27 60 L38 65 L27 69 M93 60 L82 65 L93 69"
            fill="none"
            stroke="#8c6544"
            strokeWidth="4"
          />
        )}
        {animal === "dragon" && (
          <>
            <path d="M53 38 L60 29 L67 38" fill="#f1d18b" />
            <ellipse cx="60" cy="80" rx="25" ry="14" fill="#d3dda4" />
          </>
        )}
        {(animal === "cow" || animal === "pig" || animal === "horse") && (
          <>
            <ellipse
              cx="60"
              cy={animal === "horse" ? 88 : 78}
              rx={animal === "pig" ? 20 : 23}
              ry="14"
              fill={animal === "horse" ? "#e6c6a1" : "#e9b7a1"}
            />
            <path
              d={
                animal === "horse"
                  ? "M51 84 v3 M69 84 v3"
                  : "M51 76 v2 M69 76 v2"
              }
            />
          </>
        )}
        <path d="M46 61 v3 M74 61 v3" strokeWidth="4.5" />
        <ellipse cx="38" cy="71" rx="6" ry="3" fill="#e3a08d" stroke="none" />
        <ellipse cx="82" cy="71" rx="6" ry="3" fill="#e3a08d" stroke="none" />
        {animal === "rooster" ? (
          <>
            <path d="M53 73 L60 84 L67 73 Z" fill="#deb461" />
            <path d="M58 84 Q49 101 60 99 Q71 101 62 84" fill="#db8d78" />
          </>
        ) : (
          <>
            {!["cow", "pig", "horse", "dragon", "snake"].includes(animal) && (
              <path d="M57 73 L60 76 L63 73 Z" fill="#405849" />
            )}
            <path
              d={
                animal === "horse"
                  ? "M54 96 Q60 101 66 96"
                  : "M54 83 Q60 88 66 83"
              }
              fill="none"
              strokeWidth="2"
            />
          </>
        )}
        {animal === "rat" && (
          <>
            <path d="M56 86 v8 h8 v-8" fill="#fffaf0" />
            <path d="M23 74 L36 77 M84 77 L97 74" strokeWidth="2" />
          </>
        )}
        {animal === "snake" && (
          <>
            <path
              d="M60 87 V98 M60 98 L55 102 M60 98 L65 102"
              stroke="#cc8475"
            />
            <path
              d="M52 41 L60 36 L68 41 L60 47 Z"
              fill="#e4d594"
              stroke="none"
            />
          </>
        )}
      </g>
    </svg>
  );
}
