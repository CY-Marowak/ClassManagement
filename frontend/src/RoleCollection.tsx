import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "./api";
import { StudentAvatar } from "./StudentAvatar";
import { studentRoleNames, type StudentRole } from "./studentRoles";
import { createRequestId } from "./requestId";

type Collection = {
  selected: StudentRole;
  point_balance: number;
  owned: StudentRole[];
  catalog: { id: StudentRole; name: string; price: number }[];
};
type Purchase = { role: StudentRole; request_id: string };

export function RoleCollection({
  onBack,
  onSelected,
  onBusy,
  studentId,
  onBalance,
}: {
  onBack: () => void;
  onSelected: (role: StudentRole) => void;
  onBusy: (busy: boolean) => void;
  studentId: number;
  onBalance: (balance: number) => void;
}) {
  const [collection, setCollection] = useState<Collection | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [preview, setPreview] = useState<StudentRole | null>(null);
  const previewPanel = useRef<HTMLElement>(null);
  const previewTrigger = useRef<HTMLButtonElement | null>(null);
  useEffect(() => {
    if (preview) {
      previewPanel.current?.focus();
      previewPanel.current?.scrollIntoView({ block: "center" });
    }
  }, [preview]);
  const storageKey = `cm-role-purchase-${studentId}`;
  const [pending, setPending] = useState<Purchase | null>(() => {
    try {
      const value = JSON.parse(sessionStorage.getItem(storageKey) || "null");
      return value &&
        typeof value.request_id === "string" &&
        Object.hasOwn(studentRoleNames, value.role)
        ? value
        : null;
    } catch {
      return null;
    }
  });
  const version = useRef(0);
  const reload = useCallback(async () => {
    const current = ++version.current;
    setBusy(true);
    setError("");
    try {
      const data = await api<Collection>("/student/roles/");
      if (current !== version.current) return;
      setCollection(data);
      onSelected(data.selected);
      onBalance(data.point_balance);
    } catch (e) {
      if (current !== version.current) return;
      setCollection(null);
      setError(e instanceof Error ? e.message : "無法載入角色收藏。");
    } finally {
      if (current === version.current) setBusy(false);
    }
  }, [onSelected, onBalance]);
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
      onBalance(data.point_balance);
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

  async function purchase() {
    if (busy || (!pending && !preview)) return;
    const request = pending || {
      role: preview!,
      request_id: createRequestId(),
    };
    setBusy(true);
    setError("");
    setNotice("");
    try {
      sessionStorage.setItem(storageKey, JSON.stringify(request));
      setPending(request);
      await api("/student/roles/purchases/", "POST", request);
      sessionStorage.removeItem(storageKey);
      setPending(null);
      setPreview(null);
      setNotice(
        `${studentRoleNames[request.role]}已加入收藏，可自行免費換上。`,
      );
      await reload();
    } catch (e) {
      if (e instanceof ApiError && e.status === 400) {
        sessionStorage.removeItem(storageKey);
        setPending(null);
        setPreview(null);
        await reload();
      }
      if (e instanceof ApiError && (e.status === 403 || e.status === 404))
        setCollection(null);
      setError(
        e instanceof Error ? e.message : "未能確認購買結果，請重試這次購買。",
      );
    } finally {
      setBusy(false);
    }
  }
  const product = collection?.catalog.find(({ id }) => id === preview);

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
      {pending && (
        <div className="purchase-confirmation">
          <p>
            有一筆{studentRoleNames[pending.role]}
            角色購買等待確認；重試不會重複扣點。
          </p>
          <button
            className="primary"
            disabled={busy}
            onClick={() => void purchase()}
          >
            重試這次購買
          </button>
        </div>
      )}
      {collection && (
        <>
          <p className="shop-balance">
            可用點數 <strong>{collection.point_balance}</strong>
          </p>
          {product && !pending && (
            <section
              ref={previewPanel}
              tabIndex={-1}
              className="purchase-confirmation"
              aria-label="確認購買角色"
            >
              <StudentAvatar animal={product.id} />
              <h2>收藏{product.name}角色</h2>
              <p>
                價格 <strong>{product.price}</strong> 點
              </p>
              {collection.point_balance >= product.price ? (
                <p>
                  預計餘額{" "}
                  <strong>{collection.point_balance - product.price}</strong> 點
                </p>
              ) : (
                <p className="error">
                  點數不足，還需要 {product.price - collection.point_balance}{" "}
                  點。
                </p>
              )}
              <p className="muted">
                購買後保留原角色，不會自動換上。送出時以最新可用點數確認。
              </p>
              <div className="actions">
                <button
                  className="primary"
                  disabled={busy || collection.point_balance < product.price}
                  onClick={() => void purchase()}
                >
                  確認購買 · {product.price} 點
                </button>
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() => {
                    setPreview(null);
                    previewTrigger.current?.focus();
                  }}
                >
                  取消
                </button>
              </div>
            </section>
          )}
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
            {collection.catalog.map(({ id, name, price }) => (
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
                {!collection.owned.includes(id) && (
                  <>
                    <p className="muted small">{price} 點</p>
                    <button
                      className="secondary"
                      disabled={busy || !!pending}
                      onClick={(event) => {
                        previewTrigger.current = event.currentTarget;
                        setPreview(id);
                        setNotice("");
                        setError("");
                      }}
                    >
                      預覽{name}
                    </button>
                  </>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
