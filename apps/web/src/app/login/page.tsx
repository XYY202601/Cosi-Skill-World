"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { BrandMark } from "@/components/app-graphics";
import { useAuth } from "@/lib/auth-context";
import { MOCK_USERS } from "@/lib/mock-users";

const ROLE_COPY: Record<string, string> = {
  learner: "进入个人训练、复盘和成长页",
  supervisor: "查看团队训练表现与重点风险",
  organization_admin: "管理组织训练计划与运营数据",
  content_admin: "维护内容、策略和训练资产",
  platform_admin: "管理平台级配置与系统运行状态",
};

export default function LoginPage() {
  const router = useRouter();
  const { user, authMode, isLoading, login } = useAuth();
  const [userId, setUserId] = useState("org_admin_demo");
  const [password, setPassword] = useState("Welcome123");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isLoading && user) {
      router.replace("/");
    }
  }, [isLoading, router, user]);

  const selectedUser = MOCK_USERS.find((candidate) => candidate.id === userId) ?? null;

  const handleLogin = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!userId.trim()) {
        return;
      }
      setError(null);
      const loginError = await login(userId.trim(), password);
      if (loginError) {
        setError(loginError);
        return;
      }
      router.replace("/");
      router.refresh();
    },
    [login, password, router, userId],
  );

  if (isLoading || user) {
    return (
      <div className="login-loading-shell">
        <div className="login-loading-card">
          <p>Checking session...</p>
        </div>
      </div>
    );
  }

  if (authMode === "oidc") {
    return (
      <>
        <div className="login-shell">
          <div className="login-backdrop" />
          <div className="login-layout">
            <section className="login-story">
              <div className="login-brand">
                <span className="login-brand-mark">
                  <BrandMark className="login-brand-icon" />
                </span>
                <div>
                  <p className="login-eyebrow">Cosi Skill World</p>
                  <h1>训练系统入口</h1>
                </div>
              </div>
              <div className="login-story-copy">
                <p className="login-kicker">MR Visit JP Training Gym</p>
                <h2>使用组织账号登录训练工作台。</h2>
                <p>通过 SSO 身份提供商安全登录。</p>
              </div>
            </section>
            <section className="login-panel">
              <div className="login-panel-card">
                <div className="login-panel-header">
                  <h3>SSO 登录</h3>
                  <span>当前认证模式：OIDC SSO</span>
                </div>
                <a className="login-submit login-oidc-link" href="/api/auth/oidc/login">
                  通过身份提供商登录
                </a>
              </div>
            </section>
          </div>
        </div>
        <style jsx>{`
          .login-oidc-link {
            display: flex;
            align-items: center;
            justify-content: center;
            text-decoration: none;
            margin-top: 8px;
          }
        `}</style>
      </>
    );
  }

  return (
    <>
      <div className="login-shell">
        <div className="login-backdrop" />
        <div className="login-layout">
          <section className="login-story">
            <div className="login-brand">
              <span className="login-brand-mark">
                <BrandMark className="login-brand-icon" />
              </span>
              <div>
                <p className="login-eyebrow">Cosi Skill World</p>
                <h1>训练系统入口</h1>
              </div>
            </div>

            <div className="login-story-copy">
              <p className="login-kicker">MR Visit JP Training Gym</p>
              <h2>把训练、复盘与团队运营放到同一个工作台里。</h2>
              <p>
                登录后可以直接进入训练场景、查看个人成长、追踪团队表现，以及维护训练计划。
              </p>
            </div>

            <div className="login-feature-grid">
              <article className="login-feature-card">
                <strong>真实训练闭环</strong>
                <span>场景练习、即时复盘、成长跟踪一体化。</span>
              </article>
              <article className="login-feature-card">
                <strong>团队可见性</strong>
                <span>主管可以快速识别高风险 learner 和重复短板。</span>
              </article>
              <article className="login-feature-card">
                <strong>计划驱动训练</strong>
                <span>把目标技能、场景和学习人群组织成可追踪计划。</span>
              </article>
            </div>

            <div className="login-role-strip">
              {MOCK_USERS.filter((item) => item.role !== "learner").map((item) => (
                <div
                  className={`login-role-chip ${item.id === userId ? "is-active" : ""}`}
                  key={item.id}
                >
                  <span>{item.role}</span>
                  <strong>{item.name}</strong>
                </div>
              ))}
            </div>
          </section>

          <section className="login-panel">
            <div className="login-panel-card">
              <div className="login-panel-header">
                <p className="login-eyebrow">Secure Access</p>
                <h3>登录账户</h3>
                <span>
                  当前认证模式：{authMode === "mock" ? "Mock Session" : "Disabled"}
                </span>
              </div>

              {error ? <div className="login-error-banner">{error}</div> : null}

              <form className="login-form" onSubmit={handleLogin}>
                <label className="login-field">
                  <span>账号</span>
                  <select
                    id="userId"
                    value={userId}
                    onChange={(e) => {
                      setUserId(e.target.value);
                      setError(null);
                    }}
                  >
                    {MOCK_USERS.map((candidate) => (
                      <option key={candidate.id} value={candidate.id}>
                        {candidate.label}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="login-field">
                  <span>密码</span>
                  <input
                    id="password"
                    type="password"
                    value={password}
                    onChange={(e) => {
                      setPassword(e.target.value);
                      setError(null);
                    }}
                    autoComplete="current-password"
                  />
                </label>

                <div className="login-user-preview">
                  <div>
                    <p>当前身份</p>
                    <strong>{selectedUser?.name ?? "未选择用户"}</strong>
                  </div>
                  <div>
                    <p>权限范围</p>
                    <strong>{selectedUser?.role ?? "-"}</strong>
                  </div>
                  <div className="login-user-preview-wide">
                    <p>进入后可用</p>
                    <strong>{selectedUser ? ROLE_COPY[selectedUser.role] ?? "进入系统主页" : "-"}</strong>
                  </div>
                </div>

                <button className="login-submit" disabled={!userId.trim()} type="submit">
                  进入工作台
                </button>
              </form>

              <div className="login-footer-note">
                <span>默认密码：`Welcome123`</span>
                <span>推荐先用“组织管理者”查看训练计划与数据面板。</span>
              </div>
            </div>
          </section>
        </div>
      </div>

      <style jsx>{`
        .login-loading-shell {
          min-height: 100vh;
          display: flex;
          align-items: center;
          justify-content: center;
          background:
            radial-gradient(circle at top left, rgba(237, 116, 73, 0.2), transparent 28%),
            radial-gradient(circle at bottom right, rgba(28, 104, 94, 0.2), transparent 24%),
            linear-gradient(135deg, #f6efe7 0%, #f8f7f3 48%, #edf4ee 100%);
        }

        .login-loading-card {
          padding: 18px 24px;
          border: 1px solid rgba(17, 36, 77, 0.08);
          border-radius: 18px;
          background: rgba(255, 255, 255, 0.82);
          box-shadow: 0 24px 60px rgba(30, 41, 59, 0.08);
          color: #39506f;
        }

        .login-shell {
          position: relative;
          min-height: 100vh;
          overflow: hidden;
          background:
            radial-gradient(circle at top left, rgba(236, 116, 66, 0.28), transparent 22%),
            radial-gradient(circle at 85% 20%, rgba(30, 120, 110, 0.18), transparent 18%),
            linear-gradient(135deg, #f6eadf 0%, #f7f4ed 42%, #ecf3ee 100%);
        }

        .login-backdrop {
          position: absolute;
          inset: 0;
          background-image:
            linear-gradient(rgba(17, 36, 77, 0.04) 1px, transparent 1px),
            linear-gradient(90deg, rgba(17, 36, 77, 0.04) 1px, transparent 1px);
          background-size: 32px 32px;
          mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.7), transparent 92%);
          pointer-events: none;
        }

        .login-layout {
          position: relative;
          min-height: 100vh;
          display: grid;
          grid-template-columns: minmax(0, 1.2fr) minmax(360px, 460px);
          gap: 28px;
          align-items: stretch;
          padding: 28px;
        }

        .login-story,
        .login-panel-card {
          border: 1px solid rgba(17, 36, 77, 0.08);
          box-shadow: 0 28px 80px rgba(33, 48, 76, 0.09);
          backdrop-filter: blur(18px);
        }

        .login-story {
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          padding: 40px;
          border-radius: 36px;
          background:
            linear-gradient(180deg, rgba(255, 255, 255, 0.82), rgba(255, 248, 243, 0.88));
        }

        .login-brand {
          display: flex;
          align-items: center;
          gap: 16px;
        }

        .login-brand-mark {
          width: 56px;
          height: 56px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          border-radius: 18px;
          background: linear-gradient(135deg, #17355f 0%, #24536d 100%);
          box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.14);
        }

        .login-brand-icon {
          width: 24px;
          height: 24px;
        }

        .login-eyebrow {
          margin: 0 0 4px;
          font-size: 0.74rem;
          letter-spacing: 0.16em;
          text-transform: uppercase;
          color: #7c6b57;
          font-weight: 700;
        }

        .login-brand h1,
        .login-story-copy h2,
        .login-panel-header h3 {
          margin: 0;
          color: #12284d;
        }

        .login-brand h1 {
          font-size: clamp(1.8rem, 2vw, 2.4rem);
        }

        .login-story-copy {
          max-width: 720px;
        }

        .login-kicker {
          margin: 0 0 12px;
          font-size: 0.85rem;
          font-weight: 800;
          letter-spacing: 0.12em;
          text-transform: uppercase;
          color: #bf5a32;
        }

        .login-story-copy h2 {
          font-size: clamp(1.5rem, 2.8vw, 3rem);
          line-height: 1.1;
          max-width: 22ch;
          margin-bottom: 18px;
        }

        .login-story-copy p {
          margin: 0;
          max-width: 56ch;
          font-size: 1rem;
          line-height: 1.75;
          color: #516682;
        }

        .login-feature-grid {
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: 16px;
        }

        .login-feature-card {
          padding: 20px;
          border-radius: 22px;
          background: rgba(255, 255, 255, 0.72);
          border: 1px solid rgba(17, 36, 77, 0.08);
        }

        .login-feature-card strong,
        .login-role-chip strong,
        .login-user-preview strong {
          display: block;
          color: #12284d;
        }

        .login-feature-card span,
        .login-role-chip span,
        .login-panel-header span,
        .login-footer-note span,
        .login-user-preview p {
          color: #5f7188;
        }

        .login-feature-card strong,
        .login-role-chip strong {
          margin-bottom: 8px;
        }

        .login-feature-card span,
        .login-role-chip span,
        .login-footer-note span,
        .login-user-preview p {
          font-size: 0.92rem;
          line-height: 1.5;
        }

        .login-role-strip {
          display: grid;
          grid-template-columns: repeat(4, minmax(0, 1fr));
          gap: 14px;
        }

        .login-role-chip {
          padding: 18px;
          border-radius: 20px;
          border: 1px solid rgba(17, 36, 77, 0.08);
          background: rgba(255, 255, 255, 0.55);
          transition: transform 0.2s ease, border-color 0.2s ease, background 0.2s ease;
        }

        .login-role-chip.is-active {
          background: linear-gradient(135deg, rgba(23, 53, 95, 0.98), rgba(38, 84, 108, 0.94));
          border-color: transparent;
          transform: translateY(-2px);
        }

        .login-role-chip.is-active strong,
        .login-role-chip.is-active span {
          color: #f6f1e9;
        }

        .login-panel {
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .login-panel-card {
          width: 100%;
          padding: 34px;
          border-radius: 32px;
          background: rgba(255, 255, 255, 0.88);
        }

        .login-panel-header {
          margin-bottom: 24px;
        }

        .login-panel-header h3 {
          margin-bottom: 8px;
          font-size: 2rem;
        }

        .login-error-banner {
          margin-bottom: 18px;
          padding: 14px 16px;
          border-radius: 16px;
          border: 1px solid rgba(185, 28, 28, 0.18);
          background: rgba(254, 242, 242, 0.92);
          color: #b42318;
          font-size: 0.94rem;
        }

        .login-form {
          display: flex;
          flex-direction: column;
          gap: 18px;
        }

        .login-field {
          display: flex;
          flex-direction: column;
          gap: 9px;
        }

        .login-field span {
          font-size: 0.92rem;
          font-weight: 700;
          color: #284363;
        }

        .login-field input,
        .login-field select {
          height: 52px;
          width: 100%;
          padding: 0 16px;
          border: 1px solid rgba(17, 36, 77, 0.12);
          border-radius: 16px;
          background: rgba(248, 250, 252, 0.96);
          color: #11244d;
          transition: border-color 0.2s ease, box-shadow 0.2s ease, background 0.2s ease;
        }

        .login-field input:focus,
        .login-field select:focus {
          outline: none;
          border-color: rgba(191, 90, 50, 0.55);
          box-shadow: 0 0 0 4px rgba(191, 90, 50, 0.12);
          background: #ffffff;
        }

        .login-user-preview {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 12px;
          margin-top: 4px;
        }

        .login-user-preview > div {
          padding: 14px 16px;
          border-radius: 18px;
          background: rgba(242, 246, 250, 0.9);
          border: 1px solid rgba(17, 36, 77, 0.08);
        }

        .login-user-preview-wide {
          grid-column: 1 / -1;
        }

        .login-user-preview p {
          margin: 0 0 6px;
        }

        .login-user-preview strong {
          line-height: 1.45;
        }

        .login-submit {
          height: 56px;
          margin-top: 8px;
          border: 0;
          border-radius: 18px;
          background: linear-gradient(135deg, #bf5a32 0%, #17355f 100%);
          color: #fffdf9;
          font-weight: 800;
          font-size: 1rem;
          cursor: pointer;
          transition: transform 0.18s ease, box-shadow 0.18s ease, opacity 0.18s ease;
          box-shadow: 0 18px 40px rgba(23, 53, 95, 0.2);
        }

        .login-submit:hover {
          transform: translateY(-1px);
          box-shadow: 0 24px 54px rgba(23, 53, 95, 0.24);
        }

        .login-submit:disabled {
          cursor: not-allowed;
          opacity: 0.55;
          transform: none;
          box-shadow: none;
        }

        .login-footer-note {
          display: flex;
          flex-direction: column;
          gap: 6px;
          margin-top: 22px;
          padding-top: 18px;
          border-top: 1px solid rgba(17, 36, 77, 0.08);
        }

        @media (max-width: 1120px) {
          .login-layout {
            grid-template-columns: 1fr;
          }

          .login-story-copy h2 {
            max-width: 22ch;
          }

          .login-feature-grid,
          .login-role-strip {
            grid-template-columns: repeat(2, minmax(0, 1fr));
          }
        }

        @media (max-width: 720px) {
          .login-layout {
            padding: 16px;
          }

          .login-story,
          .login-panel-card {
            padding: 22px;
            border-radius: 24px;
          }

          .login-story-copy h2 {
            font-size: 2.2rem;
            max-width: none;
          }

          .login-feature-grid,
          .login-role-strip,
          .login-user-preview {
            grid-template-columns: 1fr;
          }
        }
      `}</style>
    </>
  );
}
