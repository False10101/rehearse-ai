"use client";

import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect } from "react";

import { useAuth } from "@/components/auth/auth-provider";

const publicRoutes = new Set(["/", "/auth/callback"]);

function ProtectedRouteBoundary({ children }: Readonly<{ children: ReactNode }>) {
  const pathname = usePathname();
  const router = useRouter();
  const { isAuthenticated, isLoading } = useAuth();
  const isPublicRoute = publicRoutes.has(pathname);

  useEffect(() => {
    if (isLoading) return;

    if (!isAuthenticated && !isPublicRoute) {
      router.replace("/");
      return;
    }

  }, [isAuthenticated, isLoading, isPublicRoute, pathname, router]);

  if (!isPublicRoute && (isLoading || !isAuthenticated)) return null;

  return children;
}

export function AuthRouteGuard({ children }: Readonly<{ children: ReactNode }>) {
  return <ProtectedRouteBoundary>{children}</ProtectedRouteBoundary>;
}
