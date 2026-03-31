<script lang="ts">
	import { goto } from '$app/navigation';
	import { api } from '$lib/api';
	import type { GroupRead, GroupCreate, GroupUpdate, Stream, Profile, ProfilePermission } from '$lib/types';

	// ── State ────────────────────────────────────────────────────────────────
	let loading = $state(true);
	let groups = $state<GroupRead[]>([]);
	let streams = $state<Stream[]>([]);
	let profileMap = $state<Record<number, Profile[]>>({});

	// Create group form
	let showCreateForm = $state(false);
	let createForm = $state<GroupCreate>({ name: '', role: 'user', profile_ids: [], oidc_group_names: [] });
	let createError = $state<string | null>(null);
	let creating = $state(false);

	// Edit group state
	let editingGroupId = $state<number | null>(null);
	let editForm = $state<GroupUpdate>({});
	let editError = $state<string | null>(null);
	let saving = $state(false);

	// Delete confirmation
	let deleteGroupId = $state<number | null>(null);
	let deleting = $state(false);

	// Profile access modal
	let profileAccessGroupId = $state<number | null>(null);
	let profilePerms = $state<Map<number, ProfilePermission>>(new Map());
	let savingProfiles = $state(false);

	// OIDC mapping editor
	let mappingGroupId = $state<number | null>(null);
	let mappingInput = $state('');
	let mappingNames = $state<string[]>([]);
	let savingMappings = $state(false);

	// ── Auth guard & data loading ────────────────────────────────────────────
	$effect(() => {
		api.getMe().then((me) => {
			if (me.role !== 'admin') { goto('/'); return; }
			loadData();
		}).catch(() => goto('/'));
	});

	async function loadData() {
		try {
			const [g, s] = await Promise.all([api.getGroups(), api.getStreams()]);
			groups = g;
			streams = s;
			const pMap: Record<number, Profile[]> = {};
			for (const stream of s) {
				pMap[stream.id] = await api.getStreamProfiles(stream.id);
			}
			profileMap = pMap;
		} catch (err) {
			console.error('Failed to load data:', err);
		} finally {
			loading = false;
		}
	}

	// ── Create ───────────────────────────────────────────────────────────────
	async function handleCreate() {
		creating = true;
		createError = null;
		try {
			const created = await api.createGroup(createForm);
			groups = [...groups, created];
			showCreateForm = false;
			createForm = { name: '', role: 'user', profile_ids: [], oidc_group_names: [] };
		} catch (err) {
			createError = err instanceof Error ? err.message : 'Failed to create group';
		} finally {
			creating = false;
		}
	}

	// ── Edit ─────────────────────────────────────────────────────────────────
	function startEdit(group: GroupRead) {
		editingGroupId = group.id;
		editForm = { name: group.name, role: group.role };
		editError = null;
	}

	function cancelEdit() {
		editingGroupId = null;
		editForm = {};
		editError = null;
	}

	async function saveEdit(groupId: number) {
		saving = true;
		editError = null;
		try {
			const updated = await api.updateGroup(groupId, editForm);
			groups = groups.map((g) => (g.id === groupId ? updated : g));
			editingGroupId = null;
		} catch (err) {
			editError = err instanceof Error ? err.message : 'Failed to update group';
		} finally {
			saving = false;
		}
	}

	// ── Delete ───────────────────────────────────────────────────────────────
	async function confirmDelete() {
		if (deleteGroupId === null) return;
		deleting = true;
		try {
			await api.deleteGroup(deleteGroupId);
			groups = groups.filter((g) => g.id !== deleteGroupId);
		} catch (err) {
			console.error('Failed to delete group:', err);
		} finally {
			deleting = false;
			deleteGroupId = null;
		}
	}

	// ── Profile access modal ─────────────────────────────────────────────────
	function openProfileAccess(group: GroupRead) {
		profileAccessGroupId = group.id;
		const map = new Map<number, ProfilePermission>();
		for (const pp of group.profile_permissions) {
			map.set(pp.profile_id, pp);
		}
		profilePerms = map;
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
		if (profileAccessGroupId === null) return;
		savingProfiles = true;
		try {
			const updated = await api.updateGroup(profileAccessGroupId, {
				profile_permissions: [...profilePerms.values()]
			});
			groups = groups.map((g) => (g.id === updated.id ? updated : g));
			profileAccessGroupId = null;
		} catch (err) {
			console.error('Failed to save profile access:', err);
		} finally {
			savingProfiles = false;
		}
	}

	// ── OIDC mapping editor ──────────────────────────────────────────────────
	function openMappings(group: GroupRead) {
		mappingGroupId = group.id;
		mappingNames = [...group.oidc_group_names];
		mappingInput = '';
	}

	function addMapping() {
		const name = mappingInput.trim();
		if (name && !mappingNames.includes(name)) {
			mappingNames = [...mappingNames, name];
		}
		mappingInput = '';
	}

	function removeMapping(name: string) {
		mappingNames = mappingNames.filter((n) => n !== name);
	}

	async function saveMappings() {
		if (mappingGroupId === null) return;
		savingMappings = true;
		try {
			const updated = await api.updateGroup(mappingGroupId, {
				oidc_group_names: mappingNames
			});
			groups = groups.map((g) => (g.id === updated.id ? updated : g));
			mappingGroupId = null;
		} catch (err) {
			console.error('Failed to save mappings:', err);
		} finally {
			savingMappings = false;
		}
	}

	// ── Helpers ──────────────────────────────────────────────────────────────
	function allProfiles(): Profile[] {
		return Object.values(profileMap).flat();
	}
</script>

<svelte:head>
	<title>Groups — Lapsora</title>
</svelte:head>

<div class="mx-auto max-w-5xl p-4 md:p-6">
	<div class="mb-6 flex items-center justify-between">
		<h1 class="text-2xl font-bold text-white">Group Management</h1>
		<button
			onclick={() => (showCreateForm = !showCreateForm)}
			class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500"
		>
			{showCreateForm ? 'Cancel' : 'Create Group'}
		</button>
	</div>

	{#if loading}
		<p class="text-gray-400">Loading...</p>
	{:else}
		<!-- Create form -->
		{#if showCreateForm}
			<div class="mb-6 rounded-xl border border-gray-700 bg-gray-800/50 p-4">
				<h2 class="mb-3 text-lg font-medium text-white">New Group</h2>
				<form onsubmit={(e) => { e.preventDefault(); handleCreate(); }} class="space-y-3">
					<div class="grid grid-cols-2 gap-3">
						<div>
							<label for="group-name" class="mb-1 block text-sm text-gray-300">Name</label>
							<input id="group-name" type="text" bind:value={createForm.name} required
								class="w-full rounded-md border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none" />
						</div>
						<div>
							<label for="group-role" class="mb-1 block text-sm text-gray-300">Role</label>
							<select id="group-role" bind:value={createForm.role}
								class="w-full rounded-md border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none">
								<option value="user">User</option>
								<option value="admin">Admin</option>
							</select>
						</div>
					</div>
					{#if createError}
						<p class="text-sm text-red-400">{createError}</p>
					{/if}
					<button type="submit" disabled={creating}
						class="rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-green-500 disabled:opacity-50">
						{creating ? 'Creating...' : 'Create'}
					</button>
				</form>
			</div>
		{/if}

		<!-- Groups table -->
		{#if groups.length === 0}
			<p class="text-gray-400">No groups yet. Create one to map OIDC groups to Lapsora permissions.</p>
		{:else}
			<div class="overflow-x-auto rounded-xl border border-gray-700">
				<table class="w-full text-left text-sm text-gray-300">
					<thead class="border-b border-gray-700 bg-gray-800/80 text-xs uppercase text-gray-400">
						<tr>
							<th class="px-4 py-3">Name</th>
							<th class="px-4 py-3">Role</th>
							<th class="px-4 py-3">Profiles</th>
							<th class="px-4 py-3">OIDC Mappings</th>
							<th class="px-4 py-3 text-right">Actions</th>
						</tr>
					</thead>
					<tbody class="divide-y divide-gray-700/50">
						{#each groups as group (group.id)}
							<tr class="hover:bg-gray-800/30">
								{#if editingGroupId === group.id}
									<td class="px-4 py-3">
										<input type="text" bind:value={editForm.name}
											class="w-full rounded border border-gray-600 bg-gray-800 px-2 py-1 text-sm text-white" />
									</td>
									<td class="px-4 py-3">
										<select bind:value={editForm.role}
											class="rounded border border-gray-600 bg-gray-800 px-2 py-1 text-sm text-white">
											<option value="user">User</option>
											<option value="admin">Admin</option>
										</select>
									</td>
									<td class="px-4 py-3">{group.profile_ids.length}</td>
									<td class="px-4 py-3">{group.oidc_group_names.length}</td>
									<td class="px-4 py-3 text-right">
										{#if editError}<span class="mr-2 text-xs text-red-400">{editError}</span>{/if}
										<button onclick={() => saveEdit(group.id)} disabled={saving}
											class="mr-1 text-green-400 hover:text-green-300 text-xs">Save</button>
										<button onclick={cancelEdit}
											class="text-gray-400 hover:text-gray-300 text-xs">Cancel</button>
									</td>
								{:else}
									<td class="px-4 py-3 font-medium text-white">{group.name}</td>
									<td class="px-4 py-3">
										<span class="rounded-full px-2 py-0.5 text-xs {group.role === 'admin' ? 'bg-purple-500/20 text-purple-300' : 'bg-blue-500/20 text-blue-300'}">
											{group.role}
										</span>
									</td>
									<td class="px-4 py-3">{group.profile_ids.length} profile{group.profile_ids.length !== 1 ? 's' : ''}</td>
									<td class="px-4 py-3">
										{#if group.oidc_group_names.length === 0}
											<span class="text-gray-500">None</span>
										{:else}
											{#each group.oidc_group_names as name}
												<span class="mr-1 mb-1 inline-block rounded bg-gray-700 px-2 py-0.5 text-xs text-gray-300">{name}</span>
											{/each}
										{/if}
									</td>
									<td class="px-4 py-3 text-right">
										<button onclick={() => startEdit(group)} class="mr-1 text-blue-400 hover:text-blue-300 text-xs">Edit</button>
										<button onclick={() => openProfileAccess(group)} class="mr-1 text-yellow-400 hover:text-yellow-300 text-xs">Profiles</button>
										<button onclick={() => openMappings(group)} class="mr-1 text-cyan-400 hover:text-cyan-300 text-xs">Mappings</button>
										<button onclick={() => (deleteGroupId = group.id)} class="text-red-400 hover:text-red-300 text-xs">Delete</button>
									</td>
								{/if}
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}
	{/if}
</div>

<!-- Profile Access Modal -->
{#if profileAccessGroupId !== null}
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onclick={() => (profileAccessGroupId = null)} onkeydown={() => {}}>
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="max-h-[80vh] w-full max-w-2xl overflow-y-auto rounded-xl border border-gray-700 bg-gray-900 p-6" onclick={(e) => e.stopPropagation()} onkeydown={() => {}}>
			<h2 class="mb-4 text-lg font-medium text-white">Profile Access & Permissions — {groups.find((g) => g.id === profileAccessGroupId)?.name}</h2>
			<div class="mb-3 text-xs text-gray-500">
				<span class="inline-block w-16">View</span>
				<span class="inline-block w-16">Export</span>
				<span class="inline-block w-16">Timelapse</span>
				<span class="inline-block w-16">Manage</span>
			</div>
			{#each streams as stream (stream.id)}
				<div class="mb-3">
					<h3 class="mb-1 text-sm font-medium text-gray-300">{stream.name}</h3>
					{#if profileMap[stream.id]?.length}
						{#each profileMap[stream.id] as profile (profile.id)}
							{@const pp = profilePerms.get(profile.id)}
							<div class="flex items-center gap-2 py-1 text-sm text-gray-400">
								<input type="checkbox" checked={profilePerms.has(profile.id)}
									onchange={() => toggleProfile(profile.id)}
									class="rounded border-gray-600 bg-gray-800 text-blue-500" />
								<span class="w-32 truncate">{profile.name}</span>
								{#if pp}
									<label class="flex items-center gap-1 w-16">
										<input type="checkbox" checked={pp.can_view} onchange={() => togglePerm(profile.id, 'can_view')} class="h-3 w-3 rounded border-gray-600 bg-gray-800 text-green-500" />
										<span class="text-xs">View</span>
									</label>
									<label class="flex items-center gap-1 w-16">
										<input type="checkbox" checked={pp.can_export} onchange={() => togglePerm(profile.id, 'can_export')} class="h-3 w-3 rounded border-gray-600 bg-gray-800 text-yellow-500" />
										<span class="text-xs">Export</span>
									</label>
									<label class="flex items-center gap-1 w-16">
										<input type="checkbox" checked={pp.can_timelapse} onchange={() => togglePerm(profile.id, 'can_timelapse')} class="h-3 w-3 rounded border-gray-600 bg-gray-800 text-cyan-500" />
										<span class="text-xs">TL</span>
									</label>
									<label class="flex items-center gap-1 w-16">
										<input type="checkbox" checked={pp.can_manage} onchange={() => togglePerm(profile.id, 'can_manage')} class="h-3 w-3 rounded border-gray-600 bg-gray-800 text-purple-500" />
										<span class="text-xs">Manage</span>
									</label>
								{/if}
							</div>
						{/each}
					{:else}
						<p class="text-xs text-gray-500">No profiles</p>
					{/if}
				</div>
			{/each}
			<div class="mt-4 flex justify-end gap-2">
				<button onclick={() => (profileAccessGroupId = null)}
					class="rounded-lg border border-gray-600 px-4 py-2 text-sm text-gray-300 hover:bg-gray-800">Cancel</button>
				<button onclick={saveProfileAccess} disabled={savingProfiles}
					class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50">
					{savingProfiles ? 'Saving...' : 'Save'}
				</button>
			</div>
		</div>
	</div>
{/if}

<!-- OIDC Mapping Modal -->
{#if mappingGroupId !== null}
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onclick={() => (mappingGroupId = null)} onkeydown={() => {}}>
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="w-full max-w-lg rounded-xl border border-gray-700 bg-gray-900 p-6" onclick={(e) => e.stopPropagation()} onkeydown={() => {}}>
			<h2 class="mb-4 text-lg font-medium text-white">OIDC Group Mappings — {groups.find((g) => g.id === mappingGroupId)?.name}</h2>
			<p class="mb-3 text-sm text-gray-400">Map OIDC group names from your identity provider to this Lapsora group. Users in matching OIDC groups will receive this group's role and profile access on login.</p>

			<div class="mb-3 flex gap-2">
				<input type="text" bind:value={mappingInput} placeholder="OIDC group name"
					onkeydown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addMapping(); } }}
					class="flex-1 rounded-md border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none" />
				<button onclick={addMapping}
					class="rounded-lg bg-gray-700 px-3 py-2 text-sm text-white hover:bg-gray-600">Add</button>
			</div>

			{#if mappingNames.length === 0}
				<p class="text-sm text-gray-500">No OIDC groups mapped yet.</p>
			{:else}
				<div class="flex flex-wrap gap-2">
					{#each mappingNames as name}
						<span class="inline-flex items-center gap-1 rounded-full bg-gray-700 px-3 py-1 text-sm text-gray-300">
							{name}
							<button onclick={() => removeMapping(name)} class="ml-1 text-gray-400 hover:text-red-400">×</button>
						</span>
					{/each}
				</div>
			{/if}

			<div class="mt-4 flex justify-end gap-2">
				<button onclick={() => (mappingGroupId = null)}
					class="rounded-lg border border-gray-600 px-4 py-2 text-sm text-gray-300 hover:bg-gray-800">Cancel</button>
				<button onclick={saveMappings} disabled={savingMappings}
					class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50">
					{savingMappings ? 'Saving...' : 'Save Mappings'}
				</button>
			</div>
		</div>
	</div>
{/if}

<!-- Delete Group Confirmation Modal -->
{#if deleteGroupId !== null}
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onclick={() => { if (!deleting) deleteGroupId = null; }} onkeydown={() => {}}>
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="mx-4 w-full max-w-sm rounded-xl bg-gray-900 p-6 shadow-xl" onclick={(e) => e.stopPropagation()} onkeydown={() => {}}>
			<h3 class="mb-2 text-lg font-semibold text-red-400">Delete Group</h3>
			<p class="mb-2 text-sm text-gray-300">
				Are you sure you want to delete <strong class="text-white">{groups.find((g) => g.id === deleteGroupId)?.name}</strong>?
			</p>
			<p class="mb-4 text-sm text-gray-400">
				This will remove the group's profile access and OIDC mappings. Users in this group will lose any permissions granted through it.
			</p>
			<div class="flex justify-end gap-3">
				<button
					onclick={() => { deleteGroupId = null; }}
					disabled={deleting}
					class="rounded-lg border border-gray-700 px-4 py-2 text-sm text-gray-300 hover:bg-gray-800 disabled:opacity-50"
				>
					Cancel
				</button>
				<button
					onclick={confirmDelete}
					disabled={deleting}
					class="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-500 disabled:opacity-50"
				>
					{deleting ? 'Deleting...' : 'Delete Group'}
				</button>
			</div>
		</div>
	</div>
{/if}
