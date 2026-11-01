import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "./api";
import { StudentAvatar } from "./StudentAvatar";
import { studentRoleNames, type StudentRole } from "./studentRoles";

type Collection = {
  selected: StudentRole;
  owned: StudentRole[];
  catalog: { id: StudentRole; name: string }[];
};

export function RoleCollection({
  onBack,
  onSelected,
  onBusy,
}: {
  onBack: () => void;
  onSelected: (role: StudentRole) => void;
  onBusy: (busy: boolean) => void;
}) {
  const [collection, setCollection] = useState<Collection | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const version = useRef(0);
  const reload = useCallback(async () => {
    const current = ++version.current;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const data = await api<Collection>("/student/roles/");
      if (current !== version.current) return;
      setCollection(data);
      onSelected(data.selected);
    } catch (e) {
      if (current !== version.current) return;
      setCollection(null);
      setError(e instanceof Error ? e.message : "無法載入角色收藏。");
    } finally {
      if (current === version.current) setBusy(false);
    }
  }, [onSelected]);
  useEffect(() => {
    void reload();
    return () => {
      version.current++;
    };
  }, [reload]);
  useEffect(() => {
    onBusy(busy);
  }, [busy, onBusy]);

  async function select(role: StudentRole) {
    if (busy) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const data = await api<Collection>("/student/roles/", "POST", { role });
      setCollection(data);
      onSelected(data.selected);
      setNotice(`已換上${studentRoleNames[data.selected]}角色。`);
    } catch (e) {
      if (e instanceof ApiError && (e.status === 403 || e.status === 404))
        setCollection(null);
      setError(
        e instanceof Error ? e.message : "無法確認選用結果，請更新收藏後再試。",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section
      className="role-collection"
      aria-label="我的角色收藏"
      aria-busy={busy}
    >
      <div className="page-title">
        <button className="text-button" onClick={onBack} disabled={busy}>
          返回我的頁面
        </button>
        <button
          className="secondary"
          onClick={() => void reload()}
          disabled={busy}
        >
          更新收藏
        </button>
      </div>
      <p className="eyebrow">我的動物夥伴</p>
      <h1>我的角色收藏</h1>
      <p className="muted">已擁有的角色可免費更換，收藏會一直保留。</p>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="notice" role="status">
          {notice}
        </p>
      )}
      {busy && <p role="status">正在更新角色收藏…</p>}
      {collection && (
        <>
          <div className="current-role" aria-label="目前使用角色">
            <StudentAvatar animal={collection.selected} />
            <p>
              目前使用 <strong>{studentRoleNames[collection.selected]}</strong>
            </p>
          </div>
          <h2>已擁有 · {collection.owned.length} 種</h2>
          <ul className="role-grid" aria-label="已擁有角色">
            {collection.catalog
              .filter(({ id }) => collection.owned.includes(id))
              .map(({ id, name }) => (
                <li className="role-card" key={id}>
                  <StudentAvatar animal={id} />
                  <h3>{name}</h3>
                  <button
                    className="secondary"
                    disabled={busy || id === collection.selected}
                    onClick={() => void select(id)}
                  >
                    {id === collection.selected ? "目前使用中" : `換上${name}`}
                  </button>
                </li>
              ))}
          </ul>
          <h2>全部角色 · {collection.catalog.length} 種</h2>
          <p className="muted small">十二生肖與貓，共十三位夥伴。</p>
          <ul className="role-grid" aria-label="全部角色">
            {collection.catalog.map(({ id, name }) => (
              <li className="role-card" key={id}>
                <StudentAvatar animal={id} />
                <h3>{name}</h3>
                <span
                  className={
                    collection.owned.includes(id) ? "badge" : "muted small"
                  }
                >
                  {id === collection.selected
                    ? "使用中"
                    : collection.owned.includes(id)
                      ? "已擁有"
                      : "尚未擁有"}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
