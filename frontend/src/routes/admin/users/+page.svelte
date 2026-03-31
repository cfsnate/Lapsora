<script lang="ts">
	import { goto } from '$app/navigation';
	import { api } from '$lib/api';
	import type { UserAdminRead, UserCreate, UserUpdate, Stream, Profile, ProfilePermission, GroupRead } from '$lib/types';

	// ── State ────────────────────────────────────────────────────────────────
	let loading = $state(true);
	let currentUserId = $state<number | null>(null);

	let users = $state<UserAdminRead[]>([]);
	let streams = $state<Stream[]>([]);
	// map streamId -> Profile[]
	let profileMap = $state<Record<number, Profile[]>>({});

	// Create user form
	let showCreateForm = $state(false);
	let createForm = $state<UserCreate>({ username: '', display_name: '', password: '', role: 'user', email: '' });
	let createError = $state<string | null>(null);
	let creating = $state(false);

	// Edit user state
	let editingUserId = $state<number | null>(null);
	let editForm = $state<UserUpdate & { password?: string }>({});
	let editError = $state<string | null>(null);
	let saving = $state(false);

	// Profile access modal
	let profileAccessUserId = $state<number | null>(null);
	let profilePerms = $state<Map<number, ProfilePermission>>(new Map());
	let savingProfiles = $state(false);
	let profilesError = $state<string | null>(null);

	// Group membership modal
	let groupMembershipUserId = $state<number | null>(null);
	let allGroups = $state<GroupRead[]>([]);
	let selectedGroupIds = $state<Set<number>>(new Set());
	let savingGroups = $state(false);
	let groupsError = $state<string | null>(null);

	// General action feedback
	let actionMessage = $state<string | null>(null);
	let actionError = $state<string | null>(null);

	// ── Init ─────────────────────────────────────────────────────────────────
	$effect(() => {
		api.getMe()
			.then((me) => {
				if (me.role !== 'admin') {
					goto('/');
					return;
				}
				currentUserId = me.id;
				return Promise.all([api.getUsers(), api.getStreams(), api.getGroups()]);
			})
			.then((results) => {
				if (!results) return;
				const [fetchedUsers, fetchedStreams, fetchedGroups] = results;
				users = fetchedUsers;
				streams = fetchedStreams;
				allGroups = fetchedGroups;
				// Load profiles for all streams
				return Promise.all(fetchedStreams.map((s) => api.getStreamProfiles(s.id).then((profiles) => ({ streamId: s.id, profiles }))));
			})
			.then((streamProfiles) => {
				if (!streamProfiles) return;
				const map: Record<number, Profile[]> = {};
				for (const { streamId, profiles } of streamProfiles) {
					map[streamId] = profiles;
				}
				profileMap = map;
			})
			.finally(() => {
				loading = false;
			});
	});

	// ── Helpers ───────────────────────────────────────────────────────────────
	function allProfiles(): Profile[] {
		return Object.values(profileMap).flat();
	}

	function flashSuccess(msg: string) {
		actionMessage = msg;
		actionError = null;
		setTimeout(() => { actionMessage = null; }, 3000);
	}

	function flashError(msg: string) {
		actionError = msg;
		actionMessage = null;
		setTimeout(() => { actionError = null; }, 5000);
	}

	async function refreshUsers() {
		users = await api.getUsers();
	}

	// ── Create user ───────────────────────────────────────────────────────────
	async function handleCreate() {
		createError = null;
		creating = true;
		try {
			const payload: UserCreate = {
				username: createForm.username.trim(),
				display_name: createForm.display_name.trim(),
				password: createForm.password,
				role: createForm.role || 'user'
			};
			if (createForm.email?.trim()) payload.email = createForm.email.trim();
			await api.createUser(payload);
			await refreshUsers();
			showCreateForm = false;
			createForm = { username: '', display_name: '', password: '', role: 'user', email: '' };
			flashSuccess('User created successfully.');
		} catch (e: unknown) {
			if (e instanceof Response || (e && typeof e === 'object' && 'status' in e)) {
				const resp = e as Response;
				if (resp.status === 409) {
					createError = 'Username already exists.';
				} else {
					createError = `Error ${resp.status}: failed to create user.`;
				}
			} else {
				createError = 'Failed to create user.';
			}
		} finally {
			creating = false;
		}
	}

	// ── Edit user ─────────────────────────────────────────────────────────────
	function startEdit(user: UserAdminRead) {
		editingUserId = user.id;
		editForm = {
			display_name: user.display_name,
			email: user.email ?? '',
			role: user.role,
			password: ''
		};
		editError = null;
	}

	function cancelEdit() {
		editingUserId = null;
		editForm = {};
		editError = null;
	}

	async function handleSaveEdit(userId: number) {
		editError = null;
		saving = true;
		try {
			const payload: UserUpdate = {};
			if (editForm.display_name !== undefined) payload.display_name = editForm.display_name;
			if (editForm.email !== undefined) payload.email = editForm.email || null as unknown as string;
			if (editForm.role !== undefined) payload.role = editForm.role;
			if (editForm.password) payload.password = editForm.password;
			await api.updateUser(userId, payload);
			await refreshUsers();
			cancelEdit();
			flashSuccess('User updated.');
		} catch (e: unknown) {
			editError = 'Failed to save changes.';
		} finally {
			saving = false;
		}
	}

	// ── Disable / Enable ──────────────────────────────────────────────────────
	async function handleDisable(userId: number) {
		if (userId === currentUserId) {
			flashError('You cannot disable your own account.');
			return;
		}
		try {
			await api.disableUser(userId);
			await refreshUsers();
			flashSuccess('User disabled.');
		} catch (e: unknown) {
			if (e instanceof Response || (e && typeof e === 'object' && 'status' in e)) {
				const resp = e as Response;
				if (resp.status === 400) {
					flashError('Cannot disable yourself.');
				} else {
					flashError('Failed to disable user.');
				}
			} else {
				flashError('Failed to disable user.');
			}
		}
	}

	async function handleEnable(userId: number) {
		try {
			await api.updateUser(userId, { is_active: true });
			await refreshUsers();
			flashSuccess('User enabled.');
		} catch {
			flashError('Failed to enable user.');
		}
	}

	// ── Profile access ────────────────────────────────────────────────────────
	async function openProfileAccess(user: UserAdminRead) {
		profileAccessUserId = user.id;
		profilesError = null;
		try {
			const result = await api.getUserProfiles(user.id);
			const map = new Map<number, ProfilePermission>();
			for (const pp of result.profile_permissions) {
				map.set(pp.profile_id, pp);
			}
			profilePerms = map;
		} catch {
			profilesError = 'Failed to load profile access.';
		}
	}

	function closeProfileAccess() {
		profileAccessUserId = null;
		profilePerms = new Map();
		profilesError = null;
	}

	function toggleProfile(profileId: number) {
		const next = new Map(profilePerms);
		if (next.has(profileId)) {
			next.delete(profileId);
		} else {
			next.set(profileId, { profile_id: profileId, can_view: true, can_export: false, can_timelapse: false, can_manage: false });
		}
		profilePerms = next;
	}

	function togglePerm(profileId: number, perm: keyof ProfilePermission) {
		if (perm === 'profile_id') return;
		const pp = profilePerms.get(profileId);
		if (!pp) return;
		const next = new Map(profilePerms);
		next.set(profileId, { ...pp, [perm]: !pp[perm] });
		profilePerms = next;
	}

	async function saveProfileAccess() {
		if (profileAccessUserId === null) return;
		savingProfiles = true;
		profilesError = null;
		try {
			await api.setUserProfiles(profileAccessUserId, {
				profile_ids: [],
				profile_permissions: [...profilePerms.values()],
			});
			await refreshUsers();
			closeProfileAccess();
			flashSuccess('Profile access updated.');
		} catch {
			profilesError = 'Failed to save profile access.';
		} finally {
			savingProfiles = false;
		}
	}

	// ── Derived helpers ───────────────────────────────────────────────────────
	function profileAccessUser(): UserAdminRead | undefined {
		return users.find((u) => u.id === profileAccessUserId);
	}

	// ── Group membership ──────────────────────────────────────────────────────
	async function openGroupMembership(user: UserAdminRead) {
		groupMembershipUserId = user.id;
		groupsError = null;
		try {
			const result = await api.getUserGroups(user.id);
			selectedGroupIds = new Set(result.group_ids);
		} catch {
			groupsError = 'Failed to load group membership.';
		}
	}

	function closeGroupMembership() {
		groupMembershipUserId = null;
		selectedGroupIds = new Set();
		groupsError = null;
	}

	function toggleGroup(groupId: number) {
		const next = new Set(selectedGroupIds);
		if (next.has(groupId)) next.delete(groupId); else next.add(groupId);
		selectedGroupIds = next;
	}

	async function saveGroupMembership() {
		if (groupMembershipUserId === null) return;
		savingGroups = true;
		groupsError = null;
		try {
			await api.setUserGroups(groupMembershipUserId, { group_ids: [...selectedGroupIds] });
			await refreshUsers();
			closeGroupMembership();
			flashSuccess('Group membership updated.');
		} catch {
			groupsError = 'Failed to save group membership.';
		} finally {
			savingGroups = false;
		}
	}

	function groupMembershipUser(): UserAdminRead | undefined {
		return users.find((u) => u.id === groupMembershipUserId);
	}
</script>

<div class="space-y-6">
	<!-- Header -->
	<div class="flex items-center justify-between">
		<div>
			<h1 class="text-2xl font-bold text-white">User Management</h1>
			<p class="text-sm text-gray-400 mt-1">Manage users, roles, and profile access.</p>
		</div>
		<button
			onclick={() => { showCreateForm = !showCreateForm; createError = null; }}
			class="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 transition-colors"
		>
			<svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
				<path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
			</svg>
			{showCreateForm ? 'Cancel' : 'Add User'}
		</button>
	</div>

	<!-- Flash messages -->
	{#if actionMessage}
		<div class="rounded-lg bg-green-900/40 border border-green-700 px-4 py-3 text-green-300 text-sm">{actionMessage}</div>
	{/if}
	{#if actionError}
		<div class="rounded-lg bg-red-900/40 border border-red-700 px-4 py-3 text-red-300 text-sm">{actionError}</div>
	{/if}

	<!-- Create user form -->
	{#if showCreateForm}
		<div class="bg-gray-900 rounded-xl border border-gray-800 p-6">
			<h2 class="text-lg font-semibold text-white mb-4">Create New User</h2>
			{#if createError}
				<div class="mb-4 rounded-lg bg-red-900/40 border border-red-700 px-4 py-3 text-red-300 text-sm">{createError}</div>
			{/if}
			<div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
				<div>
					<label class="block text-sm font-medium text-gray-300 mb-1" for="create-username">Username <span class="text-red-400">*</span></label>
					<input
						id="create-username"
						type="text"
						bind:value={createForm.username}
						class="w-full rounded-lg bg-gray-800 border border-gray-700 text-white px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
						placeholder="username"
					/>
				</div>
				<div>
					<label class="block text-sm font-medium text-gray-300 mb-1" for="create-displayname">Display Name <span class="text-red-400">*</span></label>
					<input
						id="create-displayname"
						type="text"
						bind:value={createForm.display_name}
						class="w-full rounded-lg bg-gray-800 border border-gray-700 text-white px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
						placeholder="Display Name"
					/>
				</div>
				<div>
					<label class="block text-sm font-medium text-gray-300 mb-1" for="create-password">Password <span class="text-red-400">*</span></label>
					<input
						id="create-password"
						type="password"
						bind:value={createForm.password}
						class="w-full rounded-lg bg-gray-800 border border-gray-700 text-white px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
						placeholder="••••••••"
					/>
				</div>
				<div>
					<label class="block text-sm font-medium text-gray-300 mb-1" for="create-email">Email</label>
					<input
						id="create-email"
						type="email"
						bind:value={createForm.email}
						class="w-full rounded-lg bg-gray-800 border border-gray-700 text-white px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
						placeholder="user@example.com"
					/>
				</div>
				<div>
					<label class="block text-sm font-medium text-gray-300 mb-1" for="create-role">Role</label>
					<select
						id="create-role"
						bind:value={createForm.role}
						class="w-full rounded-lg bg-gray-800 border border-gray-700 text-white px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
					>
						<option value="user">User</option>
						<option value="admin">Admin</option>
					</select>
				</div>
			</div>
			<div class="mt-4 flex gap-3">
				<button
					onclick={handleCreate}
					disabled={creating || !createForm.username || !createForm.display_name || !createForm.password}
					class="rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed px-4 py-2 text-sm font-medium text-white transition-colors"
				>
					{creating ? 'Creating…' : 'Create User'}
				</button>
				<button
					onclick={() => { showCreateForm = false; createError = null; }}
					class="rounded-lg bg-gray-700 hover:bg-gray-600 px-4 py-2 text-sm font-medium text-gray-200 transition-colors"
				>
					Cancel
				</button>
			</div>
		</div>
	{/if}

	<!-- User list -->
	<div class="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
		{#if loading}
			<div class="p-8 text-center text-gray-400 text-sm">Loading users…</div>
		{:else if users.length === 0}
			<div class="p-8 text-center text-gray-400 text-sm">No users found.</div>
		{:else}
			<table class="min-w-full divide-y divide-gray-800">
				<thead class="bg-gray-800/50">
					<tr>
						<th class="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">User</th>
						<th class="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">Email</th>
						<th class="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">Role</th>
						<th class="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">Status</th>
						<th class="px-6 py-3 text-right text-xs font-medium text-gray-400 uppercase tracking-wider">Actions</th>
					</tr>
				</thead>
				<tbody class="divide-y divide-gray-800">
					{#each users as user (user.id)}
						<tr class="hover:bg-gray-800/30 transition-colors">
							{#if editingUserId === user.id}
								<!-- Edit row -->
								<td colspan="5" class="px-6 py-4">
									<div class="space-y-3">
										{#if editError}
											<div class="rounded-lg bg-red-900/40 border border-red-700 px-3 py-2 text-red-300 text-sm">{editError}</div>
										{/if}
										<div class="flex flex-wrap gap-3">
											<div>
												<label class="block text-xs text-gray-400 mb-1">Display Name</label>
												<input
													type="text"
													bind:value={editForm.display_name}
													class="rounded-lg bg-gray-800 border border-gray-700 text-white px-3 py-1.5 text-sm focus:outline-none focus:border-blue-500 w-48"
												/>
											</div>
											<div>
												<label class="block text-xs text-gray-400 mb-1">Email</label>
												<input
													type="email"
													bind:value={editForm.email}
													class="rounded-lg bg-gray-800 border border-gray-700 text-white px-3 py-1.5 text-sm focus:outline-none focus:border-blue-500 w-48"
												/>
											</div>
											<div>
												<label class="block text-xs text-gray-400 mb-1">Role</label>
												<select
													bind:value={editForm.role}
													class="rounded-lg bg-gray-800 border border-gray-700 text-white px-3 py-1.5 text-sm focus:outline-none focus:border-blue-500"
												>
													<option value="user">User</option>
													<option value="admin">Admin</option>
												</select>
											</div>
											<div>
												<label class="block text-xs text-gray-400 mb-1">New Password (optional)</label>
												<input
													type="password"
													bind:value={editForm.password}
													class="rounded-lg bg-gray-800 border border-gray-700 text-white px-3 py-1.5 text-sm focus:outline-none focus:border-blue-500 w-48"
													placeholder="Leave blank to keep"
												/>
											</div>
										</div>
										<div class="flex gap-2 mt-2">
											<button
												onclick={() => handleSaveEdit(user.id)}
												disabled={saving}
												class="rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 px-3 py-1.5 text-sm font-medium text-white transition-colors"
											>
												{saving ? 'Saving…' : 'Save'}
											</button>
											<button
												onclick={cancelEdit}
												class="rounded-lg bg-gray-700 hover:bg-gray-600 px-3 py-1.5 text-sm font-medium text-gray-200 transition-colors"
											>
												Cancel
											</button>
										</div>
									</div>
								</td>
							{:else}
								<!-- Normal row -->
								<td class="px-6 py-4">
									<div class="text-sm font-medium text-white">{user.display_name}</div>
									<div class="text-xs text-gray-400">@{user.username}</div>
								</td>
								<td class="px-6 py-4 text-sm text-gray-400">{user.email ?? '—'}</td>
								<td class="px-6 py-4">
									{#if user.role === 'admin'}
										<span class="inline-flex items-center rounded-full bg-purple-900/40 border border-purple-700 px-2.5 py-0.5 text-xs font-medium text-purple-300">Admin</span>
									{:else}
										<span class="inline-flex items-center rounded-full bg-gray-700/60 border border-gray-600 px-2.5 py-0.5 text-xs font-medium text-gray-300">User</span>
									{/if}
								</td>
								<td class="px-6 py-4">
									{#if user.is_active}
										<span class="inline-flex items-center rounded-full bg-green-900/40 border border-green-700 px-2.5 py-0.5 text-xs font-medium text-green-300">Active</span>
									{:else}
										<span class="inline-flex items-center rounded-full bg-red-900/40 border border-red-700 px-2.5 py-0.5 text-xs font-medium text-red-300">Disabled</span>
									{/if}
								</td>
								<td class="px-6 py-4">
									<div class="flex items-center justify-end gap-2 flex-wrap">
										<button
											onclick={() => startEdit(user)}
											class="rounded-lg bg-gray-700 hover:bg-gray-600 px-3 py-1.5 text-xs font-medium text-gray-200 transition-colors"
										>
											Edit
										</button>
										{#if user.is_active}
											<button
												onclick={() => handleDisable(user.id)}
												class="rounded-lg bg-red-700 hover:bg-red-600 px-3 py-1.5 text-xs font-medium text-white transition-colors"
											>
												Disable
											</button>
										{:else}
											<button
												onclick={() => handleEnable(user.id)}
												class="rounded-lg bg-green-700 hover:bg-green-600 px-3 py-1.5 text-xs font-medium text-white transition-colors"
											>
												Enable
											</button>
										{/if}
										{#if user.role !== 'admin'}
											<button
												onclick={() => openProfileAccess(user)}
												class="rounded-lg bg-blue-700 hover:bg-blue-600 px-3 py-1.5 text-xs font-medium text-white transition-colors"
											>
												Profiles
											</button>
											<button
												onclick={() => openGroupMembership(user)}
												class="rounded-lg bg-cyan-700 hover:bg-cyan-600 px-3 py-1.5 text-xs font-medium text-white transition-colors"
											>
												Groups
											</button>
										{/if}
									</div>
								</td>
							{/if}
						</tr>
					{/each}
				</tbody>
			</table>
		{/if}
	</div>
</div>

<!-- Profile Access Modal -->
{#if profileAccessUserId !== null}
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
		<div class="w-full max-w-2xl mx-4 bg-gray-900 rounded-xl border border-gray-800 shadow-2xl">
			<div class="flex items-center justify-between p-6 border-b border-gray-800">
				<div>
					<h2 class="text-lg font-semibold text-white">Profile Access & Permissions</h2>
					{#if profileAccessUser()}
						<p class="text-sm text-gray-400 mt-0.5">{profileAccessUser()!.display_name} (@{profileAccessUser()!.username})</p>
					{/if}
				</div>
				<button
					onclick={closeProfileAccess}
					class="text-gray-400 hover:text-white transition-colors"
					aria-label="Close"
				>
					<svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
					</svg>
				</button>
			</div>

			<div class="p-6 max-h-96 overflow-y-auto">
				{#if profilesError}
					<div class="mb-4 rounded-lg bg-red-900/40 border border-red-700 px-4 py-3 text-red-300 text-sm">{profilesError}</div>
				{/if}

				{#if streams.length === 0 || allProfiles().length === 0}
					<p class="text-gray-400 text-sm">No streams or profiles configured.</p>
				{:else}
					<div class="mb-3 text-xs text-gray-500">
						<span class="inline-block w-16">View</span>
						<span class="inline-block w-16">Export</span>
						<span class="inline-block w-16">Timelapse</span>
						<span class="inline-block w-16">Manage</span>
					</div>
					<div class="space-y-4">
						{#each streams as stream (stream.id)}
							{#if profileMap[stream.id]?.length}
								<div>
									<h3 class="text-sm font-medium text-gray-300 mb-2">{stream.name}</h3>
									<div class="space-y-2 pl-2">
										{#each profileMap[stream.id] as profile (profile.id)}
											{@const pp = profilePerms.get(profile.id)}
											<div class="flex items-center gap-2">
												<input
													type="checkbox"
													checked={profilePerms.has(profile.id)}
													onchange={() => toggleProfile(profile.id)}
													class="h-4 w-4 rounded border-gray-600 bg-gray-800 text-blue-500 focus:ring-blue-500"
												/>
												<span class="text-sm text-gray-300 w-32 truncate">{profile.name}</span>
												{#if pp}
													<label class="flex items-center gap-1 w-16">
														<input type="checkbox" checked={pp.can_view} onchange={() => togglePerm(profile.id, 'can_view')} class="h-3 w-3 rounded border-gray-600 bg-gray-800 text-green-500" />
														<span class="text-xs text-gray-500">View</span>
													</label>
													<label class="flex items-center gap-1 w-16">
														<input type="checkbox" checked={pp.can_export} onchange={() => togglePerm(profile.id, 'can_export')} class="h-3 w-3 rounded border-gray-600 bg-gray-800 text-yellow-500" />
														<span class="text-xs text-gray-500">Export</span>
													</label>
													<label class="flex items-center gap-1 w-16">
														<input type="checkbox" checked={pp.can_timelapse} onchange={() => togglePerm(profile.id, 'can_timelapse')} class="h-3 w-3 rounded border-gray-600 bg-gray-800 text-cyan-500" />
														<span class="text-xs text-gray-500">TL</span>
													</label>
													<label class="flex items-center gap-1 w-16">
														<input type="checkbox" checked={pp.can_manage} onchange={() => togglePerm(profile.id, 'can_manage')} class="h-3 w-3 rounded border-gray-600 bg-gray-800 text-purple-500" />
														<span class="text-xs text-gray-500">Manage</span>
													</label>
												{/if}
											</div>
										{/each}
									</div>
								</div>
							{/if}
						{/each}
					</div>
				{/if}
			</div>

			<div class="flex justify-end gap-3 p-6 border-t border-gray-800">
				<button
					onclick={closeProfileAccess}
					class="rounded-lg bg-gray-700 hover:bg-gray-600 px-4 py-2 text-sm font-medium text-gray-200 transition-colors"
				>
					Cancel
				</button>
				<button
					onclick={saveProfileAccess}
					disabled={savingProfiles}
					class="rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 px-4 py-2 text-sm font-medium text-white transition-colors"
				>
					{savingProfiles ? 'Saving…' : 'Save Access'}
				</button>
			</div>
		</div>
	</div>
{/if}

<!-- Group Membership Modal -->
{#if groupMembershipUserId !== null}
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
		<div class="w-full max-w-md mx-4 bg-gray-900 rounded-xl border border-gray-800 shadow-2xl">
			<div class="flex items-center justify-between p-6 border-b border-gray-800">
				<div>
					<h2 class="text-lg font-semibold text-white">Group Membership</h2>
					{#if groupMembershipUser()}
						<p class="text-sm text-gray-400 mt-0.5">{groupMembershipUser()!.display_name} (@{groupMembershipUser()!.username})</p>
					{/if}
				</div>
				<button onclick={closeGroupMembership} class="text-gray-400 hover:text-white transition-colors" aria-label="Close">
					<svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
					</svg>
				</button>
			</div>

			<div class="p-6 max-h-96 overflow-y-auto">
				{#if groupsError}
					<div class="mb-4 rounded-lg bg-red-900/40 border border-red-700 px-4 py-3 text-red-300 text-sm">{groupsError}</div>
				{/if}

				{#if allGroups.length === 0}
					<p class="text-gray-400 text-sm">No groups configured. Create groups in the Groups management page.</p>
				{:else}
					<div class="space-y-2">
						{#each allGroups as group (group.id)}
							<label class="flex items-center gap-3 rounded-lg border border-gray-800 bg-gray-800/50 p-3 cursor-pointer group">
								<input
									type="checkbox"
									checked={selectedGroupIds.has(group.id)}
									onchange={() => toggleGroup(group.id)}
									class="h-4 w-4 rounded border-gray-600 bg-gray-800 text-cyan-500 focus:ring-cyan-500"
								/>
								<div>
									<span class="text-sm text-gray-300 group-hover:text-white transition-colors">{group.name}</span>
									<span class="ml-2 text-xs {group.role === 'admin' ? 'text-purple-400' : 'text-gray-500'}">{group.role}</span>
									<span class="ml-2 text-xs text-gray-500">{group.profile_ids.length} profile{group.profile_ids.length !== 1 ? 's' : ''}</span>
								</div>
							</label>
						{/each}
					</div>
				{/if}
			</div>

			<div class="flex justify-end gap-3 p-6 border-t border-gray-800">
				<button onclick={closeGroupMembership} class="rounded-lg bg-gray-700 hover:bg-gray-600 px-4 py-2 text-sm font-medium text-gray-200 transition-colors">
					Cancel
				</button>
				<button onclick={saveGroupMembership} disabled={savingGroups} class="rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 px-4 py-2 text-sm font-medium text-white transition-colors">
					{savingGroups ? 'Saving…' : 'Save Membership'}
				</button>
			</div>
		</div>
	</div>
{/if}
