"use client";

import { Auth0Provider, useAuth0 } from "@auth0/auth0-react";
import { ReactNode, useCallback, useEffect, useRef } from "react";

const auth0Domain = process.env.NEXT_PUBLIC_AUTH0_DOMAIN;
const auth0ClientId = process.env.NEXT_PUBLIC_AUTH0_CLIENT_ID;
const auth0Audience = process.env.NEXT_PUBLIC_AUTH0_AUDIENCE;
const auth0Connection = process.env.NEXT_PUBLIC_AUTH0_CONNECTION ?? "google-oauth2";
const appUrl = process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000";
const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export const isAuth0Configured = Boolean(auth0Domain && auth0ClientId && auth0Audience);

type AuthContextValue = {
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
  if (!auth0Domain || !auth0ClientId || !auth0Audience) return children;

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
      {children}
    </Auth0Provider>
  );
}

export function useAuth(): AuthContextValue {
  const {
    error,
    getAccessTokenSilently,
    isAuthenticated,
    isLoading,
    loginWithRedirect,
    logout: logoutWithAuth0,
  } = useAuth0();

  const login = useCallback(async () => {
    await loginWithRedirect({ authorizationParams: { connection: auth0Connection } });
  }, [loginWithRedirect]);

  const logout = useCallback(() => {
    logoutWithAuth0({ logoutParams: { returnTo: appUrl } });
  }, [logoutWithAuth0]);

  const getAccessToken = useCallback(async () => {
    if (!auth0Audience) throw new Error("Sign-in is temporarily unavailable. Please try again later.");
    return getAccessTokenSilently({ authorizationParams: { audience: auth0Audience } });
  }, [getAccessTokenSilently]);

  return {
    authError: error?.message ?? null,
    isAuthenticated,
    isLoading,
    login,
    logout,
    getAccessToken,
    returnTo: "/home",
  };
}
