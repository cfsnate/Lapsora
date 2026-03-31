<script lang="ts">
	import { goto } from '$app/navigation';
	import { api } from '$lib/api';

	let username = $state('');
	let displayName = $state('');
	let email = $state('');
	let password = $state('');
	let confirmPassword = $state('');

	let submitting = $state(false);
	let error = $state('');
	let fieldErrors = $state<Record<string, string>>({});

	function validate(): boolean {
		const errors: Record<string, string> = {};
		if (!username.trim()) errors.username = 'Username is required.';
		if (!displayName.trim()) errors.displayName = 'Display name is required.';
		if (!password) errors.password = 'Password is required.';
		else if (password.length < 8) errors.password = 'Password must be at least 8 characters.';
		if (password !== confirmPassword) errors.confirmPassword = 'Passwords do not match.';
		fieldErrors = errors;
		return Object.keys(errors).length === 0;
	}

	async function handleSubmit(e: SubmitEvent) {
		e.preventDefault();
		error = '';
		fieldErrors = {};
		if (!validate()) return;

		submitting = true;
		try {
			await api.createAdmin({
				username: username.trim(),
				display_name: displayName.trim(),
				password,
				email: email.trim() || undefined
			});
			await goto('/');
		} catch (err) {
			error = err instanceof Error ? err.message : 'Setup failed. Please try again.';
		} finally {
			submitting = false;
		}
	}
</script>

<div class="flex min-h-screen items-center justify-center bg-gray-950 p-4">
	<div class="w-full max-w-md">
		<div class="mb-8 text-center">
			<h1 class="text-3xl font-bold tracking-tight text-white">Lapsora</h1>
			<p class="mt-2 text-gray-400">Create your admin account to get started.</p>
		</div>

		<div class="rounded-xl border border-gray-800 bg-gray-900 p-8 shadow-xl">
			<h2 class="mb-6 text-lg font-semibold text-white">Initial Setup</h2>

			{#if error}
				<div class="mb-4 rounded-lg border border-red-800 bg-red-900/30 px-4 py-3 text-sm text-red-300">
					{error}
				</div>
			{/if}

			<form onsubmit={handleSubmit} class="space-y-5">
				<div>
					<label for="username" class="mb-1.5 block text-sm font-medium text-gray-300">
						Username <span class="text-red-400">*</span>
					</label>
					<input
						id="username"
						type="text"
						bind:value={username}
						autocomplete="username"
						class="w-full rounded-lg border px-3 py-2 text-sm bg-gray-800 text-white placeholder-gray-500 outline-none focus:ring-2 focus:ring-blue-500 transition-colors {fieldErrors.username ? 'border-red-600' : 'border-gray-700'}"
						placeholder="admin"
					/>
					{#if fieldErrors.username}
						<p class="mt-1 text-xs text-red-400">{fieldErrors.username}</p>
					{/if}
				</div>

				<div>
					<label for="displayName" class="mb-1.5 block text-sm font-medium text-gray-300">
						Display Name <span class="text-red-400">*</span>
					</label>
					<input
						id="displayName"
						type="text"
						bind:value={displayName}
						autocomplete="name"
						class="w-full rounded-lg border px-3 py-2 text-sm bg-gray-800 text-white placeholder-gray-500 outline-none focus:ring-2 focus:ring-blue-500 transition-colors {fieldErrors.displayName ? 'border-red-600' : 'border-gray-700'}"
						placeholder="Administrator"
					/>
					{#if fieldErrors.displayName}
						<p class="mt-1 text-xs text-red-400">{fieldErrors.displayName}</p>
					{/if}
				</div>

				<div>
					<label for="email" class="mb-1.5 block text-sm font-medium text-gray-300">
						Email <span class="text-gray-500 text-xs font-normal">(optional)</span>
					</label>
					<input
						id="email"
						type="email"
						bind:value={email}
						autocomplete="email"
						class="w-full rounded-lg border border-gray-700 px-3 py-2 text-sm bg-gray-800 text-white placeholder-gray-500 outline-none focus:ring-2 focus:ring-blue-500 transition-colors"
						placeholder="you@example.com"
					/>
				</div>

				<div>
					<label for="password" class="mb-1.5 block text-sm font-medium text-gray-300">
						Password <span class="text-red-400">*</span>
					</label>
					<input
						id="password"
						type="password"
						bind:value={password}
						autocomplete="new-password"
						class="w-full rounded-lg border px-3 py-2 text-sm bg-gray-800 text-white placeholder-gray-500 outline-none focus:ring-2 focus:ring-blue-500 transition-colors {fieldErrors.password ? 'border-red-600' : 'border-gray-700'}"
						placeholder="Minimum 8 characters"
					/>
					{#if fieldErrors.password}
						<p class="mt-1 text-xs text-red-400">{fieldErrors.password}</p>
					{/if}
				</div>

				<div>
					<label for="confirmPassword" class="mb-1.5 block text-sm font-medium text-gray-300">
						Confirm Password <span class="text-red-400">*</span>
					</label>
					<input
						id="confirmPassword"
						type="password"
						bind:value={confirmPassword}
						autocomplete="new-password"
						class="w-full rounded-lg border px-3 py-2 text-sm bg-gray-800 text-white placeholder-gray-500 outline-none focus:ring-2 focus:ring-blue-500 transition-colors {fieldErrors.confirmPassword ? 'border-red-600' : 'border-gray-700'}"
						placeholder="Repeat your password"
					/>
					{#if fieldErrors.confirmPassword}
						<p class="mt-1 text-xs text-red-400">{fieldErrors.confirmPassword}</p>
					{/if}
				</div>

				<button
					type="submit"
					disabled={submitting}
					class="w-full rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-60 focus:outline-none focus:ring-2 focus:ring-blue-500"
				>
					{submitting ? 'Creating account…' : 'Create Admin Account'}
				</button>
			</form>
		</div>
	</div>
</div>
