<script setup lang="ts">
/** Written in Simplified Technical English (issue 698). The levels, the action name and the URL come
 * from the app's own definitions (the Settings section of issue 1096 and the Audit log), so the Guide
 * says what the screens say. "token", "level" and "agent" are the names; keep them when you edit. */
import { onMain } from '@/about/links'
import { ACTION_LABELS } from '@/audit/actionLabels'
import CopyValue from '@/components/settings/CopyValue.vue'
import { endpointUrl, MCP_LEVELS } from '@/views/settings/mcpTokensForm'

import GuideProse from './GuideProse.vue'

const url = endpointUrl(window.location.origin)
const TOOL_CALL = ACTION_LABELS.mcp_tool_call
const DOCS = onMain('docs/use/connect-an-ai-agent.md')
</script>

<template>
  <GuideProse>
    <p>
      An AI agent is a program that reads JAVV for you, for example to sum up the findings of a cluster. It
      connects to the MCP endpoint of JAVV with an MCP token. The endpoint is off until an admin turns it on.
      An admin makes the tokens in <span class="ui-name">Settings › AI agents (MCP)</span>.
    </p>

    <p><strong>What a token can do</strong></p>
    <ul class="levels">
      <li v-for="level in MCP_LEVELS" :key="level.value">
        <strong>{{ level.label }}.</strong> {{ level.note }}
      </li>
      <li>No token can change users, roles, settings or tokens. No token can delete data.</li>
      <li>A change by an agent gets the same checks as the same change on a screen.</li>
    </ul>

    <p><strong>An agent in the Audit log</strong></p>
    <ul>
      <li>
        The user of an agent is <code class="mono">mcp:</code> and the name of its token, for example
        <code class="mono">mcp:weekly-report</code>.
      </li>
      <li>A change by an agent writes the same rows as the same change on a screen.</li>
      <li>
        Each tool call of an agent writes one row with the action
        <span class="ui-name tool-call">{{ TOOL_CALL }}</span>. Only a user who can manage users sees these rows.
      </li>
      <li>
        <span class="ui-name">Settings › AI agents (MCP)</span> shows who made each token, and when an agent
        last used it.
      </li>
    </ul>

    <p><strong>Connect an agent</strong></p>
    <ul>
      <li>
        The URL of the endpoint of this JAVV:
        <CopyValue class="mcp-url" :value="url" copy="Copy the URL" />
      </li>
      <li>Each request sends the token in the header <code class="mono">Authorization: Bearer &lt;token&gt;</code>.</li>
      <li>
        The page <a class="docs-link" :href="DOCS" target="_blank" rel="noopener noreferrer">Connect an AI agent</a>
        gives the settings for Codex, VS Code and Cursor.
      </li>
    </ul>
  </GuideProse>
</template>

<style scoped>
.mcp-url {
  margin-top: var(--space-2);
  max-width: 560px;
}
.docs-link {
  text-decoration: underline;
  text-underline-offset: 2px;
}
.docs-link:hover {
  color: var(--ink);
}
</style>
