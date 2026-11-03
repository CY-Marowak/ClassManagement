import {
  Component,
  lazy,
  Suspense,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";
import { animalNames, type MascotAnimal } from "./AnimalAvatar";
import "./mascot-farm.css";

const Artwork = lazy(() => import("./MascotArtwork"));
const fallback = (
  <span className="farm-fallback">
    夥伴暫時休息中
    <br />
    仍可餵食與查看成長
  </span>
);
class ArtBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? fallback : this.props.children;
  }
}

export function MascotFarm({
  animal,
  level,
  feedSignal,
}: {
  animal: MascotAnimal;
  level: number;
  feedSignal: number;
}) {
  const stage = level < 5 ? 0 : level < 10 ? 1 : 2;
  const stageName = ["幼年", "成長期", "成熟"][stage];
  const scale = 1 + 0.03 * Math.min(Math.max(level - 1, 0), 20);
  const [systemStatic, setSystemStatic] = useState(
    () => matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  const [chosenStatic, setChosenStatic] = useState<boolean | null>(null);
  const isStatic = chosenStatic ?? systemStatic;
  const [hidden, setHidden] = useState(() => document.hidden);
  const [feeding, setFeeding] = useState(false);
  const consumedFeed = useRef(feedSignal);
  useEffect(() => {
    const preference = matchMedia("(prefers-reduced-motion: reduce)");
    const change = () => setSystemStatic(preference.matches);
    preference.addEventListener("change", change);
    const visibility = () => {
      setHidden(document.hidden);
    };
    document.addEventListener("visibilitychange", visibility);
    return () => {
      preference.removeEventListener("change", change);
      document.removeEventListener("visibilitychange", visibility);
    };
  }, []);
  useEffect(() => {
    const isNewFeed = feedSignal !== consumedFeed.current;
    consumedFeed.current = feedSignal;
    if (!feedSignal || !isNewFeed || hidden || isStatic) {
      setFeeding(false);
      return;
    }
    setFeeding(true);
    const timer = window.setTimeout(() => setFeeding(false), 4000);
    return () => clearTimeout(timer);
  }, [feedSignal, hidden, isStatic]);
  return (
    <>
      <div
        className={`mascot-farm${isStatic ? " farm-static" : ""}${hidden ? " farm-paused" : ""}${feeding ? " farm-feeding" : ""}`}
      >
        <div className="farm-scenery" aria-hidden="true">
          <i className="farm-sun" />
          <i className="farm-cloud" />
          <i className="farm-hill" />
          <i className="farm-fence" />
          <span className="farm-flower">✿</span>
        </div>
        <div
          className="farm-traveller"
          role="img"
          aria-label={`農場中的${animalNames[animal]} · ${stageName}`}
        >
          <div
            className="farm-size"
            style={{ "--growth-scale": scale } as CSSProperties}
          >
            <div className="farm-actor">
              <div className="farm-reaction">
                <ArtBoundary>
                  <Suspense fallback={fallback}>
                    <Artwork animal={animal} stage={stage} />
                  </Suspense>
                </ArtBoundary>
              </div>
            </div>
          </div>
        </div>
        <span className="farm-caption">我們的班級農場</span>
      </div>
      <div className="farm-controls">
        <p>
          {stageName} · {scale.toFixed(2)} 倍
        </p>
        <button
          type="button"
          className="secondary"
          aria-pressed={isStatic}
          onClick={() => setChosenStatic(!isStatic)}
        >
          {isStatic ? "動一動" : "休息一下"}
        </button>
      </div>
    </>
  );
}
