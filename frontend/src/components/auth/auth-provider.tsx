"use client";

import { Auth0Provider, useAuth0 } from "@auth0/auth0-react";
import { ReactNode, createContext, useContext, useState, useCallback, useEffect, useRef } from "react";

const auth0Domain = process.env.NEXT_PUBLIC_AUTH0_DOMAIN;
const auth0ClientId = process.env.NEXT_PUBLIC_AUTH0_CLIENT_ID;
const auth0Audience = process.env.NEXT_PUBLIC_AUTH0_AUDIENCE;
const auth0Connection = process.env.NEXT_PUBLIC_AUTH0_CONNECTION ?? "google-oauth2";
const appUrl = process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000";
const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export const isAuth0Configured = Boolean(auth0Domain && auth0ClientId && auth0Audience);

type AuthContextValue = {
  isGuest: boolean;
  startGuest: () => Promise<void>;
  authError: string | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: () => Promise<void>;
  logout: () => void;
  getAccessToken: () => Promise<string>;
  returnTo: string;
};

async function syncAuthenticatedUser(accessToken: string) {
  const response = await fetch(`${apiBaseUrl}/api/v1/auth/me`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });

  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const detail =
      typeof body === "object" && body !== null && "detail" in body && typeof body.detail === "string"
        ? ` ${body.detail}`
        : "";
    console.warn(`Rehearse AI API user sync failed with status ${response.status}.${detail}`);
  }
}

function AuthenticatedUserSync({ audience }: { audience: string }) {
  const { getAccessTokenSilently, isAuthenticated, isLoading, user } = useAuth0();
  const syncedSubject = useRef<string | null>(null);

  useEffect(() => {
    if (isLoading || !isAuthenticated || !user?.sub || syncedSubject.current === user.sub) return;
    syncedSubject.current = user.sub;

    async function syncUser() {
      try {
        const accessToken = await getAccessTokenSilently({
          authorizationParams: { audience },
        });
        await syncAuthenticatedUser(accessToken);
      } catch (error) {
        console.warn("Rehearse AI API user sync could not obtain an Auth0 access token.", error);
      }
    }

    void syncUser();
  }, [audience, getAccessTokenSilently, isAuthenticated, isLoading, user?.sub]);

  return null;
}

export function AuthProvider({ children }: Readonly<{ children: ReactNode }>) {
  if (!auth0Domain || !auth0ClientId || !auth0Audience) return <SessionProvider>{children}</SessionProvider>;

  return (
    <Auth0Provider
      authorizationParams={{
        audience: auth0Audience,
        redirect_uri: `${appUrl}/auth/callback`,
        scope: "openid profile email",
      }}
      clientId={auth0ClientId}
      domain={auth0Domain}
    >
      <AuthenticatedUserSync audience={auth0Audience} />
      <SessionProvider>{children}</SessionProvider>
    </Auth0Provider>
  );
}

const SessionContext = createContext<AuthContextValue | null>(null);
const guestStorageKey = "rehearse-guest-session";

function SessionProvider({ children }: { children: ReactNode }) {
  const {
    error,
    getAccessTokenSilently,
    isAuthenticated,
    isLoading,
    loginWithRedirect,
    logout: logoutWithAuth0,
  } = useAuth0();

  const [guestToken, setGuestToken] = useState<string | null>(null);
  const [guestLoading, setGuestLoading] = useState(true);
  useEffect(() => {
    const saved = localStorage.getItem(guestStorageKey);
    if (!saved) { setGuestLoading(false); return; }
    let active = true;
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 5000);
    void fetch(`${apiBaseUrl}/api/v1/auth/me`, { signal: controller.signal, headers: { Authorization: `Bearer ${saved}` } })
      .then(response => {
        if (!active) return;
        if (response.ok || response.status >= 500) setGuestToken(saved);
        else if (response.status === 401 || response.status === 403) localStorage.removeItem(guestStorageKey);
      }).catch(() => { if (active) setGuestToken(saved); })
      .finally(() => { window.clearTimeout(timeout); if (active) setGuestLoading(false); });
    return () => { active = false; window.clearTimeout(timeout); controller.abort(); };
  }, []);
  const startGuest = useCallback(async () => {
    const response = await fetch(`${apiBaseUrl}/api/v1/auth/guest`, { method: "POST" });
    if (!response.ok) throw new Error("Guest access could not start. Please try again.");
    const data: { access_token: string } = await response.json();
    localStorage.setItem(guestStorageKey, data.access_token);
    setGuestToken(data.access_token);
  }, []);

  const login = useCallback(async () => {
    await loginWithRedirect({ authorizationParams: { connection: auth0Connection } });
  }, [loginWithRedirect]);

  const logout = useCallback(() => {
    localStorage.removeItem(guestStorageKey);
    setGuestToken(null);
    if (isAuthenticated) logoutWithAuth0({ logoutParams: { returnTo: appUrl } });
    else if (guestToken) {
      void fetch(`${apiBaseUrl}/api/v1/auth/guest`, { method: "DELETE", headers: { Authorization: `Bearer ${guestToken}` }, keepalive: true })
        .catch(() => console.warn("Guest logout could not reach the API."))
        .finally(() => window.location.assign("/"));
    } else window.location.assign("/");
  }, [guestToken, isAuthenticated, logoutWithAuth0]);

  const getAccessToken = useCallback(async () => {
    if (!isAuthenticated && guestToken) return guestToken;
    if (!auth0Audience) throw new Error("Sign-in is temporarily unavailable. Please try again later.");
    return getAccessTokenSilently({ authorizationParams: { audience: auth0Audience } });
  }, [getAccessTokenSilently, guestToken, isAuthenticated]);

  const value: AuthContextValue = {
    isGuest: !isAuthenticated && Boolean(guestToken),
    startGuest,
    authError: error?.message ?? null,
    isAuthenticated: isAuthenticated || Boolean(guestToken),
    isLoading: guestLoading || (isAuth0Configured && isLoading),
    login,
    logout,
    getAccessToken,
    returnTo: "/home",
  };
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(SessionContext);
  if (!context) throw new Error("AuthProvider is required.");
  return context;
}
