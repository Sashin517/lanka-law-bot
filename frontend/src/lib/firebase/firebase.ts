import { initializeApp, getApps } from "firebase/app";
import { getAuth } from "firebase/auth";
import { firebaseConfig } from "./firebase-config";



const app =
  firebaseConfig.apiKey && !getApps().length
    ? initializeApp(firebaseConfig)
    : getApps()[0];

export const auth = getAuth(app);

