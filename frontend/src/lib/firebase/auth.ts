import {
  createUserWithEmailAndPassword,
  GoogleAuthProvider,
  signInWithEmailAndPassword,
  signInWithPopup,
  signOut,
  updateProfile,
  type User,
  type UserCredential,
} from "firebase/auth";

import { auth } from "./firebase";

const googleProvider = new GoogleAuthProvider();

async function establishSession(user: User) {
  const idToken = await user.getIdToken();
  const response = await fetch("/api/auth/session", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ idToken }),
  });

  if (!response.ok) {
    throw new Error("Failed to establish session");
  }
}

export async function signUpWithEmail(
  email: string,
  password: string,
  displayName: string,
) {
  const userCredential = await createUserWithEmailAndPassword(
    auth,
    email,
    password,
  );

  await updateProfile(userCredential.user, { displayName });
  await establishSession(userCredential.user);

  return userCredential;
}

export async function signInWithEmail(
  email: string,
  password: string,
): Promise<UserCredential> {
  const userCredential = await signInWithEmailAndPassword(auth, email, password);
  await establishSession(userCredential.user);
  return userCredential;
}

export async function signInWithGoogle(): Promise<UserCredential> {
  const userCredential = await signInWithPopup(auth, googleProvider);
  await establishSession(userCredential.user);
  return userCredential;
}

export async function logOut() {
  await fetch("/api/auth/logout", { method: "POST" });
  await signOut(auth);
  window.location.href = "/login";
}

export async function syncSession(user: User) {
  await establishSession(user);
}

export function getAuthErrorMessage(error: unknown): string {
  const code =
    typeof error === "object" &&
    error !== null &&
    "code" in error &&
    typeof error.code === "string"
      ? error.code
      : "";

  switch (code) {
    case "auth/email-already-in-use":
      return "An account with this email already exists.";
    case "auth/invalid-email":
      return "Please enter a valid email address.";
    case "auth/invalid-credential":
    case "auth/wrong-password":
    case "auth/user-not-found":
      return "Invalid email or password.";
    case "auth/weak-password":
      return "Password must be at least 6 characters.";
    case "auth/popup-closed-by-user":
      return "Google sign-in was cancelled.";
    case "auth/popup-blocked":
      return "Pop-up was blocked. Allow pop-ups and try again.";
    case "auth/too-many-requests":
      return "Too many attempts. Please try again later.";
    default:
      return "Something went wrong. Please try again.";
  }
}

export type { User };
