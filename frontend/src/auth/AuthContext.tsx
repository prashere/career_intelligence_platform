import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { authApi } from '../api/auth';
import { setUnauthorizedHandler } from '../api/http';
import { clearAuth, getStoredToken, getStoredUser, isAdmin, storeAuth, type AuthUser } from './storage';

interface AuthContextValue {
  user: AuthUser | null;
  token: string | null;
  isAuthenticated: boolean;
  isAdmin: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name?: string) => Promise<void>;
  logout: () => void;
  setUser: (user: AuthUser) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [token, setToken] = useState<string | null>(() => getStoredToken());
  const [user, setUserState] = useState<AuthUser | null>(() => getStoredUser());

  const login = useCallback(async (email: string, password: string) => {
    const res = await authApi.login(email, password);
    storeAuth(res.access_token, res.user);
    setToken(res.access_token);
    setUserState(res.user);
    queryClient.clear();
  }, [queryClient]);

  const register = useCallback(async (email: string, password: string, name?: string) => {
    const res = await authApi.register(email, password, name);
    storeAuth(res.access_token, res.user);
    setToken(res.access_token);
    setUserState(res.user);
    queryClient.clear();
  }, [queryClient]);

  const logout = useCallback(() => {
    clearAuth();
    setToken(null);
    setUserState(null);
    queryClient.clear();
  }, [queryClient]);

  useEffect(() => {
    setUnauthorizedHandler(logout);
    return () => setUnauthorizedHandler(null);
  }, [logout]);

  useEffect(() => {
    const storedToken = getStoredToken();
    if (!storedToken) return;

    let cancelled = false;
    authApi
      .me()
      .then((fresh) => {
        if (cancelled) return;
        setUserState(fresh);
        storeAuth(storedToken, fresh);
      })
      .catch(() => {
        if (!cancelled) logout();
      });

    return () => {
      cancelled = true;
    };
  }, [logout]);

  const setUser = useCallback((next: AuthUser) => {
    setUserState(next);
    const currentToken = getStoredToken();
    if (currentToken) storeAuth(currentToken, next);
  }, []);

  const value = useMemo(
    () => ({
      user,
      token,
      isAuthenticated: Boolean(token && user),
      isAdmin: isAdmin(user),
      login,
      register,
      logout,
      setUser,
    }),
    [user, token, login, register, logout, setUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
