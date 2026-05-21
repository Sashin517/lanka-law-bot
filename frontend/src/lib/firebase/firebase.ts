import { initializeApp, getApps } from "firebase/app";
import { getAuth } from "firebase/auth";

import { firebaseConfig } from "./firebase-config";

const app = getApps().length ? getApps()[0] : initializeApp(firebaseConfig);
export const auth = getAuth(app);
