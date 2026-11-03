import type { MascotAnimal } from "./mascotAnimals";

// Original SVG, extending the accepted cm-v2 sample. All stages share y=21..132
// and the same foot anchor; changing proportions never resets the growth scale.
export default function MascotArtwork({
  animal,
  stage,
}: {
  animal: MascotAnimal;
  stage: number;
}) {
  const fur = {
    cat: "#edc889",
    dog: "#d4b392",
    rabbit: "#fffaf0",
    cow: "#fff5df",
    horse: "#c99a78",
    pig: "#edb7aa",
  }[animal];
  const hasMuzzle = animal === "cow" || animal === "horse" || animal === "pig";
  const headY = (animal === "rabbit" ? [72, 70, 68] : [64, 61, 58])[stage];
  return (
    <svg viewBox="0 0 120 140" aria-hidden="true">
      <ellipse cx="60" cy="130" rx="37" ry="5" fill="#61784d" opacity=".16" />
      <g
        stroke="#405849"
        strokeWidth="2.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {animal === "rabbit" ? (
          <circle cx="91" cy="108" r="12" fill={fur} />
        ) : animal === "pig" ? (
          <path
            d="M85 109 Q106 110 103 99 Q100 93 95 99 Q92 105 108 101"
            fill="none"
            stroke={fur}
            strokeWidth="6"
          />
        ) : (
          <path
            d="M85 107 Q111 103 102 82"
            fill="none"
            stroke={
              animal === "cat"
                ? "#d9ab6b"
                : animal === "horse"
                  ? "#86674f"
                  : "#a98267"
            }
            strokeWidth="9"
          />
        )}
        <ellipse
          cx="60"
          cy={[102, 99, 96][stage]}
          rx={[27, 30, 32][stage]}
          ry={[25, 28, 31][stage]}
          fill={fur}
        />
        <ellipse
          cx="60"
          cy="104"
          rx="17"
          ry="19"
          fill={animal === "cat" ? "#fff0cd" : "#f5e8d8"}
          stroke="none"
        />
        <path
          className="farm-leg farm-leg-back"
          d="M38 115 L37 127 Q42 132 49 127 L49 117"
          fill={fur}
        />
        <path
          className="farm-leg"
          d="M71 117 L71 127 Q78 132 83 127 L82 115"
          fill={fur}
        />
        {animal === "cat" && (
          <>
            <path
              d="M28 55 L27 21 Q40 24 49 39 M71 39 Q80 24 93 21 L92 55"
              fill={fur}
            />
            <path
              d="M33 42 L33 30 L43 39 M77 39 L87 30 L87 42"
              fill="#dda28d"
            />
          </>
        )}
        {animal === "rabbit" && (
          <>
            <ellipse cx="43" cy="43" rx="10" ry="22" fill={fur} />
            <ellipse cx="77" cy="43" rx="10" ry="22" fill={fur} />
            <path d="M43 29 V49 M77 29 V49" stroke="#e1aaa2" strokeWidth="5" />
          </>
        )}
        {animal === "dog" && (
          <path
            d="M39 42 Q30 17 49 23 Q57 25 60 32 Q67 18 80 24 L81 45"
            fill={fur}
          />
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
        {animal === "horse" && (
          <>
            <path
              d="M34 50 Q24 12 40 23 L49 42 M71 42 L80 23 Q96 12 86 50"
              fill={fur}
            />
            <path d="M37 29 L41 42 M83 29 L79 42" stroke="#e5b8a0" />
          </>
        )}
        {animal === "pig" && (
          <>
            <path
              d="M31 54 Q17 21 34 21 L50 40 M70 40 L86 21 Q103 21 89 54"
              fill={fur}
            />
            <path
              d="M31 33 L36 44 M89 33 L84 44"
              stroke="#d99188"
              strokeWidth="4"
            />
          </>
        )}
        <ellipse
          cx="60"
          cy={headY}
          rx={[35, 33, 31][stage]}
          ry={animal === "rabbit" ? 25 : 30}
          fill={fur}
        />
        {animal === "cow" && (
          <path
            d="M36 43 Q55 30 53 58 Q44 66 32 56"
            fill="#ac8261"
            stroke="none"
          />
        )}
        {animal === "horse" && (
          <path
            d="M37 45 Q37 26 58 29 Q82 26 85 50 L72 45 L67 57 L58 44 L49 53 L49 40 Z"
            fill="#86674f"
          />
        )}
        {hasMuzzle && (
          <>
            <ellipse
              cx="60"
              cy={headY + 14}
              rx={animal === "pig" ? 20 : 23}
              ry="14"
              fill={animal === "horse" ? "#e6c6a1" : "#e9b7a1"}
            />
            <path d={`M51 ${headY + 12} v2 M69 ${headY + 12} v2`} />
          </>
        )}
        {animal === "dog" && (
          <>
            <ellipse
              cx="29"
              cy={headY - 10}
              rx="12"
              ry="22"
              fill="#a98267"
              transform={`rotate(16 29 ${headY - 10})`}
            />
            <ellipse
              cx="91"
              cy={headY - 10}
              rx="12"
              ry="22"
              fill="#a98267"
              transform={`rotate(-16 91 ${headY - 10})`}
            />
            <ellipse
              cx="60"
              cy={headY + 14}
              rx="19"
              ry="13"
              fill="#f5e8d8"
              stroke="none"
            />
          </>
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
        <path d={`M46 ${headY - 3} v3 M74 ${headY - 3} v3`} strokeWidth="4.5" />
        <ellipse
          cx="38"
          cy={headY + 7}
          rx="6"
          ry="3"
          fill="#e3a08d"
          stroke="none"
        />
        <ellipse
          cx="82"
          cy={headY + 7}
          rx="6"
          ry="3"
          fill="#e3a08d"
          stroke="none"
        />
        {!hasMuzzle && (
          <path
            d={`M57 ${headY + 9} L60 ${headY + 12} L63 ${headY + 9} Z`}
            fill="#405849"
          />
        )}
        <path
          className="farm-mouth"
          d={`M54 ${headY + 19} Q60 ${headY + 24} 66 ${headY + 19}`}
          fill="none"
          strokeWidth="2"
        />
        {stage === 1 && (
          <path
            d="M43 91 Q60 101 77 91 L66 108 L60 102 L54 108 Z"
            fill="#b2c68c"
          />
        )}
        {stage === 2 && (
          <>
            <path
              d="M39 89 Q60 99 81 89 L73 104 L60 100 L47 104 Z"
              fill="#729b7b"
            />
            <circle cx="60" cy="103" r="5" fill="#f4d38c" />
          </>
        )}
        <g className="farm-treat">
          <ellipse cx="60" cy="88" rx="13" ry="8" fill="#bd885b" />
          <path d="M55 86 h1 M64 90 h1" stroke="#fff0cb" />
        </g>
        <path
          className="farm-heart"
          d="M92 70 C76 57 86 48 92 55 C101 47 109 58 92 70"
          fill="#df927d"
          stroke="none"
        />
      </g>
    </svg>
  );
}
