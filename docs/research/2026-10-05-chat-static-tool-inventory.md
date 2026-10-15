# Static registered-tool inventory for Chat parity

2026-10-05; grounding r9 R37. AST read-only inventory of literal ToolDefinition
constructors. This is source evidence, not exhaustive dynamic plugin/MCP catalog,
installed availability or current grant proof. Runtime catalog comparison under
current scope is required by Chat tool contract. No functions executed.

| Name | Effect | Audience expression | Source |
|---|---|---|---|
| a2a_collab_list | 'read' | audiences | `app/vault_runtime/agent_network/collab/tools.py` |
| a2a_collab_turn | 'write' | audiences | `app/vault_runtime/agent_network/collab/tools.py` |
| agent2agent_list | 'read' | audiences | `app/vault_runtime/agent_network/tools.py` |
| agent2agent_send | 'write' | audiences | `app/vault_runtime/agent_network/tools.py` |
| calendar_create | 'write' | frozenset({AgentKind.VOICE, AgentKind.BACKGROUND}) | `app/vault_runtime/calendar_tools.py` |
| goal_cancel | 'write' | frozenset({AgentKind.VOICE}) | `app/vault_runtime/voice/goal_tools.py` |
| goal_inspect | 'read' | frozenset({AgentKind.VOICE}) | `app/vault_runtime/voice/goal_tools.py` |
| goal_start | 'write' | frozenset({AgentKind.VOICE}) | `app/vault_runtime/voice/goal_tools.py` |
| load_agent_skill | 'read' | frozenset({AgentKind.VOICE, AgentKind.BACKGROUND}) | `app/vault_runtime/extensions/activation.py` |
| memory_confirm_action | 'write' | frozenset({AgentKind.VOICE}) | `app/vault_runtime/memory/tools.py` |
| memory_explain | 'read' | frozenset({AgentKind.VOICE, AgentKind.BACKGROUND}) | `app/vault_runtime/memory/tools.py` |
| memory_lookup | 'read' | frozenset({AgentKind.VOICE, AgentKind.BACKGROUND}) | `app/vault_runtime/memory/tools.py` |
| memory_prepare_correction | 'write' | frozenset({AgentKind.VOICE}) | `app/vault_runtime/memory/tools.py` |
| memory_prepare_forget | 'delete' | frozenset({AgentKind.VOICE}) | `app/vault_runtime/memory/tools.py` |
| memory_remember_intent | 'write' | frozenset({AgentKind.VOICE}) | `app/vault_runtime/memory/tools.py` |
| web_search | 'read' | frozenset({AgentKind.VOICE, AgentKind.BACKGROUND}) | `app/vault_runtime/web_search.py` |
| workspace_create_directory | 'write' | frozenset({AgentKind.VOICE, AgentKind.BACKGROUND}) | `app/vault_runtime/workspace_files/tools.py` |
| workspace_delete_path | 'delete' | frozenset({AgentKind.VOICE, AgentKind.BACKGROUND}) | `app/vault_runtime/workspace_files/tools.py` |
| workspace_list_directory | 'read' | frozenset({AgentKind.VOICE, AgentKind.BACKGROUND}) | `app/vault_runtime/workspace_files/tools.py` |
| workspace_move_path | 'write' | frozenset({AgentKind.VOICE, AgentKind.BACKGROUND}) | `app/vault_runtime/workspace_files/tools.py` |
| workspace_patch_file | 'write' | frozenset({AgentKind.VOICE, AgentKind.BACKGROUND}) | `app/vault_runtime/workspace_files/tools.py` |
| workspace_read_file | 'read' | frozenset({AgentKind.VOICE, AgentKind.BACKGROUND}) | `app/vault_runtime/workspace_files/tools.py` |
| workspace_root | 'read' | frozenset({AgentKind.VOICE, AgentKind.BACKGROUND}) | `app/vault_runtime/workspace_files/tools.py` |
| workspace_save_file | 'write' | frozenset({AgentKind.VOICE, AgentKind.BACKGROUND}) | `app/vault_runtime/workspace_files/tools.py` |
| workspace_search_files | 'read' | frozenset({AgentKind.VOICE, AgentKind.BACKGROUND}) | `app/vault_runtime/workspace_files/tools.py` |
| workspace_upload_files | 'write' | frozenset({AgentKind.VOICE, AgentKind.BACKGROUND}) | `app/vault_runtime/workspace_files/tools.py` |
| workspace_write_file | 'write' | frozenset({AgentKind.VOICE, AgentKind.BACKGROUND}) | `app/vault_runtime/workspace_files/tools.py` |
