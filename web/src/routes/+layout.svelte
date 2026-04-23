<script lang="ts">
	import './layout.css';
	import favicon from '$lib/assets/favicon.svg';
	import Nav from '$lib/Nav.svelte';
	import Footer from '$lib/Footer.svelte';
	import { page } from '$app/stores';

	let { children } = $props();

	// Don't render chrome on the callback route — it briefly flashes before redirect.
	let isCallback = $derived($page.url.pathname === '/callback');
</script>

<svelte:head><link rel="icon" href={favicon} /></svelte:head>
{#if !isCallback}
	<Nav />
{/if}
{@render children()}
{#if !isCallback}
	<Footer />
{/if}
