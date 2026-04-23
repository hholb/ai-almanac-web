import { readable } from 'svelte/store';
import { browser } from '$app/environment';
import { getManager } from './auth';

/**
 * Reactive store for the current authentication state.
 * Always `false` during SSR or when auth is not configured.
 */
export const isAuthenticated = readable<boolean>(false, (set) => {
	if (!browser) return;
	const manager = getManager();
	if (!manager) return;
	set(manager.authenticated);
	const unsubscribe = manager.events.authenticated.addListener(({ isAuthenticated }) => {
		set(isAuthenticated);
	});
	return unsubscribe;
});
