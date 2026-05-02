"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState, useRef, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "@/lib/auth-context";

import "@/lib/i18n";
import { AppIcon, BrandMark, UserAvatar } from "@/components/app-graphics";

const NAV_KEYS = [
  { href: "/scenarios", key: "nav.scenarios" },
  { href: "/records", key: "nav.records" },
  { href: "/progress", key: "nav.progress" },
  { href: "/marketplace", key: "nav.marketplace" },
  { href: "/team", key: "nav.team" },
  { href: "/admin", key: "nav.admin" },
];

function activeHref(pathname: string): string {
  if (
    (pathname.startsWith("/sessions/") || pathname.startsWith("/records/")) &&
    pathname.endsWith("/review")
  ) {
    return "/progress";
  }
  if (pathname.startsWith("/sessions/") || pathname.startsWith("/records/")) {
    return "/records";
  }
  if (pathname.startsWith("/records")) {
    return "/records";
  }
  if (pathname.startsWith("/progress")) {
    return "/progress";
  }
  if (pathname.startsWith("/marketplace")) {
    return "/marketplace";
  }
  if (pathname.startsWith("/team")) {
    return "/team";
  }
  if (pathname.startsWith("/admin")) {
    return "/admin";
  }
  if (pathname.startsWith("/scenarios")) {
    return "/scenarios";
  }
  return "/";
}

export function SiteHeader() {
  const pathname = usePathname();
  const currentHref = activeHref(pathname ?? "/");
  const { t, i18n } = useTranslation();
  const { user, authMode, isLoading, logout } = useAuth();
  const router = useRouter();

  const [showNotifications, setShowNotifications] = useState(false);
  const [showProfile, setShowProfile] = useState(false);
  const [showLanguage, setShowLanguage] = useState(false);

  const notifRef = useRef<HTMLDivElement>(null);
  const profileRef = useRef<HTMLDivElement>(null);
  const langRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (notifRef.current && !notifRef.current.contains(event.target as Node)) {
        setShowNotifications(false);
      }
      if (profileRef.current && !profileRef.current.contains(event.target as Node)) {
        setShowProfile(false);
      }
      if (langRef.current && !langRef.current.contains(event.target as Node)) {
        setShowLanguage(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  if (pathname?.startsWith("/login")) return null;

  return (
    <header className="app-header">
      <Link className="app-brand" href="/">
        <BrandMark className="brand-logo" />
        <span className="app-brand-name">COSI Skill World</span>
      </Link>

      <nav aria-label="Primary" className="app-nav">
        {NAV_KEYS.map((item) => (
          <Link
            key={item.href}
            className={`app-nav-link${currentHref === item.href ? " is-active" : ""}`}
            href={item.href}
          >
            {t(item.key)}
          </Link>
        ))}
      </nav>

      <div className="app-header-tools">
        {/* Language Popover */}
        <div className="header-popover-wrapper" ref={langRef}>
          <button
            className="icon-button"
            onClick={() => setShowLanguage((prev) => !prev)}
            type="button"
          >
            <AppIcon className="icon-md" name="globe" />
          </button>
          
          <div className={`header-popover ${showLanguage ? "is-open" : ""}`} style={{ minWidth: "140px" }}>
            <div className="popover-header">{t("header.selectLanguage")}</div>
            <button
              className="popover-item"
              onClick={() => { void i18n.changeLanguage("zh"); setShowLanguage(false); }}
              style={{ color: i18n.resolvedLanguage === "zh" ? "var(--brand)" : undefined }}
              type="button"
            >
              <span>中文</span>
            </button>
            <button
              className="popover-item"
              onClick={() => { void i18n.changeLanguage("en"); setShowLanguage(false); }}
              style={{ color: i18n.resolvedLanguage === "en" ? "var(--brand)" : undefined }}
              type="button"
            >
              <span>English</span>
            </button>
            <button
              className="popover-item"
              onClick={() => { void i18n.changeLanguage("ja"); setShowLanguage(false); }}
              style={{ color: i18n.resolvedLanguage === "ja" ? "var(--brand)" : undefined }}
              type="button"
            >
              <span>日本語</span>
            </button>
          </div>
        </div>

        {/* Notifications Popover */}
        <div className="header-popover-wrapper" ref={notifRef}>
          <button
            className="icon-button"
            onClick={() => setShowNotifications((prev) => !prev)}
            type="button"
          >
            <AppIcon className="icon-md" name="bell" />
            <span className="icon-dot" />
          </button>
          
          <div className={`header-popover ${showNotifications ? "is-open" : ""}`}>
            <div className="popover-header">{t("header.notifications")} (2)</div>
            <button className="popover-item" type="button">
              <AppIcon className="icon-sm" name="clipboard" />
              <p>
                <span>{t("header.newRecord")}</span>
                <small>{t("header.newRecordDesc")}</small>
              </p>
            </button>
            <button className="popover-item" type="button">
              <AppIcon className="icon-sm" name="spark" />
              <p>
                <span>{t("header.diagnosisUpdated")}</span>
                <small>{t("header.diagnosisDesc")}</small>
              </p>
            </button>
          </div>
        </div>

        {/* User Profile Popover */}
        <div className="header-popover-wrapper" ref={profileRef}>
          {isLoading ? (
            <div className="doctor-chip" style={{ opacity: 0.5 }}>
              <UserAvatar className="doctor-chip-avatar" compact />
              <span className="doctor-chip-name">...</span>
            </div>
          ) : (authMode === "mock" || authMode === "oidc") && !user ? (
            <Link className="icon-button" href="/login" style={{ textDecoration: "none" }}>
              <AppIcon className="icon-md" name="user" />
              <span style={{ fontSize: "0.85rem", marginLeft: 6 }}>{t("header.login")}</span>
            </Link>
          ) : (
            <>
              <button
                className="doctor-chip"
                onClick={() => setShowProfile((prev) => !prev)}
                type="button"
              >
                <UserAvatar className="doctor-chip-avatar" compact />
                <span className="doctor-chip-name">{user?.name || t("header.drName")}</span>
                <AppIcon className="icon-sm" name="chevron-down" />
              </button>

              <div className={`header-popover ${showProfile ? "is-open" : ""}`}>
                {user ? (
                  <>
                    <div className="popover-header">{t("header.myAccount")}</div>
                    <div className="popover-item" style={{ cursor: "default", fontSize: "0.8em", opacity: 0.7 }}>
                      <AppIcon className="icon-md" name="user" />
                      <span>{user.role}{user.org_id ? ` · ${user.org_id}` : ""}</span>
                    </div>
                    <Link className="popover-item" href="/progress" onClick={() => setShowProfile(false)}>
                      <AppIcon className="icon-md" name="trend" />
                      <span>{t("header.progress")}</span>
                    </Link>
                    <div className="popover-divider" />
                    <button
                      className="popover-item danger"
                      type="button"
                      onClick={async () => {
                        await logout();
                        router.push("/login");
                      }}
                    >
                      <AppIcon className="icon-md" name="log-out" />
                      <span>{t("header.logout")}</span>
                    </button>
                  </>
                ) : authMode === "disabled" ? (
                  <div className="popover-item" style={{ cursor: "default" }}>
                    <AppIcon className="icon-md" name="user" />
                    <span>{t("header.drName")}</span>
                  </div>
                ) : null}
              </div>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
