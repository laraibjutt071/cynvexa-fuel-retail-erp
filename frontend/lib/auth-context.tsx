"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { ApiError, apiFetch, apiJson } from "./api";
import type { Me } from "./types";

interface AccessTokenResponse {
  access_token: string;
  token_type: string;
  expires_in_minutes: number;
}

export interface RegisterInput {
  company_name: string;
  station_name?: string;
  full_name: string;
  email: string;
  password: string;
  plan_code?: string;
}

interface AuthContextValue {
  user: Me | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  /** Self-service sign-up - creates the organization, first station, the
   * caller as its Owner, and a trial subscription, then signs them in.
   * Returns the new org/station ids so the caller can redirect directly. */
  register: (input: RegisterInput) => Promise<{ organizationId: string; stationId: string }>;
  logout: () => Promise<void>;
  /** Fetch wrapper that attaches the current access token and retries once
   * after a silent refresh if the server says the token is no longer valid. */
  authFetch: (path: string, init?: RequestInit) => Promise<Response>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  // Access token lives only in memory (a ref, not state) - it is never
  // written to localStorage/sessionStorage, which keeps it out of reach of
  // a basic XSS payload reading browser storage.
  const accessTokenRef = useRef<string | null>(null);

  const fetchMe = useCallback(async (token: string): Promise<Me> => {
    return apiJson<Me>("/auth/me", { headers: { Authorization: `Bearer ${token}` } });
  }, []);

  const refresh = useCallback(async (): Promise<string | null> => {
    const response = await apiFetch("/auth/refresh", { method: "POST" });
    if (!response.ok) return null;
    const body = (await response.json()) as AccessTokenResponse;
    accessTokenRef.current = body.access_token;
    return body.access_token;
  }, []);

  useEffect(() => {
    (async () => {
      const token = await refresh();
      if (token) {
        try {
          setUser(await fetchMe(token));
        } catch {
          accessTokenRef.current = null;
          setUser(null);
        }
      }
      setLoading(false);
    })();
  }, [refresh, fetchMe]);

  const login = useCallback(
    async (email: string, password: string) => {
      const body = await apiJson<AccessTokenResponse>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      accessTokenRef.current = body.access_token;
      setUser(await fetchMe(body.access_token));
    },
    [fetchMe]
  );

  const register = useCallback(
    async (input: RegisterInput) => {
      const body = await apiJson<AccessTokenResponse & { organization_id: string; station_id: string }>(
        "/auth/register",
        { method: "POST", body: JSON.stringify(input) }
      );
      accessTokenRef.current = body.access_token;
      setUser(await fetchMe(body.access_token));
      return { organizationId: body.organization_id, stationId: body.station_id };
    },
    [fetchMe]
  );

  const logout = useCallback(async () => {
    await apiFetch("/auth/logout", { method: "POST" });
    accessTokenRef.current = null;
    setUser(null);
  }, []);

  const authFetch = useCallback(
    async (path: string, init: RequestInit = {}): Promise<Response> => {
      const withToken = (token: string | null): RequestInit => ({
        ...init,
        headers: { ...(init.headers ?? {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      });

      let response = await apiFetch(path, withToken(accessTokenRef.current));
      if (response.status === 401) {
        const newToken = await refresh();
        if (!newToken) {
          accessTokenRef.current = null;
          setUser(null);
          throw new ApiError(401, "Your session has expired. Please log in again.");
        }
        response = await apiFetch(path, withToken(newToken));
      }
      return response;
    },
    [refresh]
  );

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, authFetch }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
