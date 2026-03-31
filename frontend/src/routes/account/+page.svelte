<script lang="ts">
	import { api } from '$lib/api';
	import type { AuthUser } from '$lib/types';

	let user = $state<AuthUser | null>(null);
	let loading = $state(true);

	// Profile form
	let displayName = $state('');
	let email = $state('');
	let savingProfile = $state(false);
	let profileResult = $state<{ ok: boolean; message: string } | null>(null);

	// Password form
	let currentPassword = $state('');
	let newPassword = $state('');
	let confirmPassword = $state('');
	let savingPassword = $state(false);
	let passwordResult = $state<{ ok: boolean; message: string } | null>(null);

	$effect(() => {
		api.getMe().then((u) => {
			user = u;
			displayName = u.display_name ?? '';
			email = u.email ?? '';
		}).catch(() => {}).finally(() => {
			loading = false;
		});
	});

	async function saveProfile() {
		savingProfile = true;
		profileResult = null;
		try {
			const updated = await api.updateMe({ display_name: displayName, email: email || undefined });
			user = updated;
			profileResult = { ok: true, message: 'Profile updated successfully.' };
		} catch (err: any) {
			profileResult = { ok: false, message: err?.message ?? 'Failed to update profile.' };
		} finally {
			savingProfile = false;
		}
	}

	async function savePassword() {
		passwordResult = null;
		if (!newPassword) {
			passwordResult = { ok: false, message: 'New password cannot be empty.' };
			return;
		}
		if (newPassword !== confirmPassword) {
			passwordResult = { ok: false, message: 'New password and confirmation do not match.' };
			return;
		}
		savingPassword = true;
		try {
			await api.updateMe({ password: newPassword });
			passwordResult = { ok: true, message: 'Password changed successfully.' };
			currentPassword = '';
			newPassword = '';
			confirmPassword = '';
		} catch (err: any) {
			passwordResult = { ok: false, message: err?.message ?? 'Failed to change password.' };
		} finally {
			savingPassword = false;
		}
	}

	function formatDate(iso: string) {
		return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' });
	}
</script>

<div class="mx-auto max-w-2xl space-y-6">
	<h1 class="text-2xl font-bold text-white">Account Settings</h1>

	{#if loading}
		<p class="text-gray-400">Loading…</p>
	{:else if user}
		<!-- Account Info (read-only) -->
		<div class="rounded-xl border border-gray-800 bg-gray-900 p-6">
			<h2 class="mb-4 text-base font-semibold text-gray-100">Account Information</h2>
			<dl class="space-y-3 text-sm">
				<div class="flex items-center justify-between">
					<dt class="text-gray-400">Username</dt>
					<dd class="font-mono text-gray-200">{user.username}</dd>
				</div>
				<div class="flex items-center justify-between">
					<dt class="text-gray-400">Role</dt>
					<dd class="rounded bg-gray-800 px-2 py-0.5 text-xs font-medium text-gray-300 capitalize">{user.role}</dd>
				</div>
				<div class="flex items-center justify-between">
					<dt class="text-gray-400">Account created</dt>
					<dd class="text-gray-200">{formatDate(user.created_at)}</dd>
				</div>
				{#if user.oidc_provider}
					<div class="flex items-center justify-between">
						<dt class="text-gray-400">Linked via</dt>
						<dd class="text-gray-200">{user.oidc_provider}</dd>
					</div>
				{/if}
			</dl>
		</div>

		<!-- Profile Section -->
		<div class="rounded-xl border border-gray-800 bg-gray-900 p-6">
			<h2 class="mb-4 text-base font-semibold text-gray-100">Profile</h2>
			<div class="space-y-4">
				<div>
					<label for="display-name" class="mb-1 block text-sm font-medium text-gray-300">Display Name</label>
					<input
						id="display-name"
						type="text"
						bind:value={displayName}
						class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
						placeholder="Your display name"
					/>
				</div>
				<div>
					<label for="email" class="mb-1 block text-sm font-medium text-gray-300">Email</label>
					<input
						id="email"
						type="email"
						bind:value={email}
						class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
						placeholder="you@example.com"
					/>
				</div>

				{#if profileResult}
					<p class="text-sm {profileResult.ok ? 'text-green-400' : 'text-red-400'}">{profileResult.message}</p>
				{/if}

				<button
					onclick={saveProfile}
					disabled={savingProfile}
					class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:opacity-50"
				>
					{savingProfile ? 'Saving…' : 'Save Profile'}
				</button>
			</div>
		</div>

		<!-- Password Section -->
		{#if !user.oidc_provider}
			<div class="rounded-xl border border-gray-800 bg-gray-900 p-6">
				<h2 class="mb-4 text-base font-semibold text-gray-100">Change Password</h2>
				<div class="space-y-4">
					<div>
						<label for="current-password" class="mb-1 block text-sm font-medium text-gray-300">Current Password</label>
						<input
							id="current-password"
							type="password"
							bind:value={currentPassword}
							class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
							placeholder="Current password"
						/>
					</div>
					<div>
						<label for="new-password" class="mb-1 block text-sm font-medium text-gray-300">New Password</label>
						<input
							id="new-password"
							type="password"
							bind:value={newPassword}
							class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
							placeholder="New password"
						/>
					</div>
					<div>
						<label for="confirm-password" class="mb-1 block text-sm font-medium text-gray-300">Confirm New Password</label>
						<input
							id="confirm-password"
							type="password"
							bind:value={confirmPassword}
							class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
							placeholder="Confirm new password"
						/>
					</div>

					{#if passwordResult}
						<p class="text-sm {passwordResult.ok ? 'text-green-400' : 'text-red-400'}">{passwordResult.message}</p>
					{/if}

					<button
						onclick={savePassword}
						disabled={savingPassword}
						class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:opacity-50"
					>
						{savingPassword ? 'Saving…' : 'Change Password'}
					</button>
				</div>
			</div>
		{:else}
			<div class="rounded-xl border border-gray-800 bg-gray-900 p-6">
				<p class="text-sm text-gray-400">Password management is not available for accounts linked via <span class="text-gray-200">{user.oidc_provider}</span>.</p>
			</div>
		{/if}
	{/if}
</div>
