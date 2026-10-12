import { requireOptionalNativeModule } from "expo-modules-core";

type Native = {
  setToken(token: string): boolean;
  getToken(): string | null;
  clearToken(): boolean;
};

// Missing in builds made before voice logging existed (and in Expo Go): everything below then quietly does nothing.
const native = requireOptionalNativeModule<Native>("QuickLogCredentials");

export const isAvailable = native != null;

export function setToken(token: string): boolean {
  try {
    return native ? native.setToken(token) : false;
  } catch {
    return false;
  }
}

export function getToken(): string | null {
  try {
    return native ? native.getToken() : null;
  } catch {
    return null;
  }
}

export function hasToken(): boolean {
  return getToken() != null;
}

export function clearToken(): boolean {
  try {
    return native ? native.clearToken() : false;
  } catch {
    return false;
  }
}
