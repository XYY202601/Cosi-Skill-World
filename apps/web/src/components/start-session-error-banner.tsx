"use client";

import Link from "next/link";
import { useTranslation } from "react-i18next";

import { AppIcon } from "@/components/app-graphics";
import type { StartSessionErrorDetails } from "@/lib/start-session-error";

type StartSessionErrorBannerProps = {
  error: StartSessionErrorDetails;
  canInstall?: boolean;
  installBusy?: boolean;
  marketplaceHref?: string;
  onInstall?: () => void;
};

const DEFAULT_MARKETPLACE_HREF = "/marketplace";

export function StartSessionErrorBanner({
  error,
  canInstall = false,
  installBusy = false,
  marketplaceHref = DEFAULT_MARKETPLACE_HREF,
  onInstall,
}: StartSessionErrorBannerProps) {
  const { t } = useTranslation();
  const showInstallActions = error.kind === "skill_not_installed";
  const displayMessage =
    error.kind === "permission" ? t("restricted.summaryOnly") : error.message;

  return (
    <div className="error-banner start-session-error-banner" role="alert">
      <strong>{displayMessage}</strong>
      {showInstallActions ? (
        <div className="start-session-error-actions">
          <Link className="ghost-button" href={marketplaceHref}>
            <AppIcon className="icon-sm" name="globe" />
            <span>{t("startErrors.openMarketplace")}</span>
          </Link>
          {canInstall && onInstall ? (
            <button
              className="primary-button"
              disabled={installBusy}
              onClick={onInstall}
              type="button"
            >
              <AppIcon className="icon-sm" name="rocket" />
              <span>
                {installBusy ? t("startErrors.installing") : t("startErrors.installNow")}
              </span>
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
