"use client";

import { onAuthStateChanged, onIdTokenChanged, type User } from "firebase/auth";

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { syncSession } from "@/lib/firebase/auth";

import { auth } from "@/lib/firebase/firebase";

interface AuthContextValue {
  user: User | null;

  loading: boolean;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);

  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const unsubscribeAuth = onAuthStateChanged(auth, (firebaseUser) => {
      setUser(firebaseUser);

      setLoading(false);
    });

    const unsubscribeToken = onIdTokenChanged(auth, async (firebaseUser) => {
      if (firebaseUser) {
        try {
          await syncSession(firebaseUser);
        } catch {
          // Session sync failed; proxy will redirect on next navigation.
        }
      }
    });

    return () => {
      unsubscribeAuth();

      unsubscribeToken();
    };
  }, []);

  const value = useMemo(
    () => ({
      user,

      loading,
    }),

    [user, loading],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }

  return context;
}
