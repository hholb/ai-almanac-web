import { authorization } from "@globus/sdk";
import type { AuthorizationManager } from "@globus/sdk/core/authorization/AuthorizationManager";

let _manager: AuthorizationManager | null = null;

export function getManager(): AuthorizationManager | null {
  // Only runs in the browser — never called during SSR.
  const client = import.meta.env.VITE_GLOBUS_CLIENT_ID;
  const redirect = import.meta.env.VITE_GLOBUS_REDIRECT_URL;

  if (!client || !redirect) {
    console.warn("auth: VITE_GLOBUS_CLIENT_ID or VITE_GLOBUS_REDIRECT_URL is not set.");
    return null;
  }

  if (!_manager) {
    _manager = authorization.create({
      client,
      redirect,
      storage: localStorage,
      scopes: "https://auth.globus.org/scopes/50964632-afc7-4d4c-abf4-b288cc18a3af/api",
    });
  }
  return _manager;
}
