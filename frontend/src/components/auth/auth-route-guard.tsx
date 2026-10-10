"use client";

import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect } from "react";

import { isAuth0Configured, useAuth } from "@/components/auth/auth-provider";

const publicRoutes = new Set(["/", "/login", "/auth/callback"]);

function ProtectedRouteBoundary({ children }: Readonly<{ children: ReactNode }>) {
  const pathname = usePathname();
  const router = useRouter();
  const { isAuthenticated, isLoading } = useAuth();
  const isPublicRoute = publicRoutes.has(pathname);

  useEffect(() => {
    if (isLoading) return;

    if (!isAuthenticated && !isPublicRoute) {
      router.replace("/login");
      return;
    }

    if (isAuthenticated && pathname === "/login") router.replace("/home");
  }, [isAuthenticated, isLoading, isPublicRoute, pathname, router]);

  if (!isPublicRoute && (isLoading || !isAuthenticated)) return null;
  if (pathname === "/login" && isAuthenticated) return null;

  return children;
}

export function AuthRouteGuard({ children }: Readonly<{ children: ReactNode }>) {
  if (!isAuth0Configured) return children;
  return <ProtectedRouteBoundary>{children}</ProtectedRouteBoundary>;
}
