<script setup lang="ts">
import { computed, ref } from 'vue'

import type { ChunkHit } from '@/types'

const props = defineProps<{
  sources?: string[]
  contexts?: ChunkHit[]
}>()

const expanded = ref<number | null>(null)

const hits = computed(() => props.contexts ?? [])
const files = computed(() => props.sources ?? [])

function toggle(index: number) {
  expanded.value = expanded.value === index ? null : index
}

function tone(similarity: number): 'high' | 'mid' | 'low' {
  if (similarity >= 0.75) return 'high'
  if (similarity >= 0.5) return 'mid'
  return 'low'
}

function percent(similarity: number): number {
  return Math.max(0, Math.min(100, Math.round(similarity * 100)))
}
</script>

<template>
  <div v-if="hits.length || files.length" class="source-panel">
    <div v-if="files.length" class="source-panel__files">
      <span class="source-panel__caption">参考来源</span>
      <span v-for="file in files" :key="file" class="file-chip">{{ file }}</span>
    </div>

    <div v-if="hits.length" class="source-panel__hits">
      <span class="source-panel__caption">检索详情（{{ hits.length }} 个片段）</span>

      <div
        v-for="(hit, index) in hits"
        :key="hit.id || index"
        class="hit"
        :class="{ 'hit--open': expanded === index }"
      >
        <button type="button" class="hit__head" @click="toggle(index)">
          <svg
            class="hit__caret"
            :class="{ 'hit__caret--open': expanded === index }"
            viewBox="0 0 16 16"
            width="12"
            height="12"
            aria-hidden="true"
          >
            <path
              d="M6 4l4 4-4 4"
              fill="none"
              stroke="currentColor"
              stroke-width="1.6"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          </svg>
          <span class="hit__name">{{ hit.source }}</span>
          <span class="hit__index">片段 #{{ hit.chunk_index }}</span>
          <span class="hit__bar">
            <span
              class="hit__bar-fill"
              :class="`hit__bar-fill--${tone(hit.similarity)}`"
              :style="{ width: `${percent(hit.similarity)}%` }"
            />
          </span>
          <span class="hit__score" :class="`hit__score--${tone(hit.similarity)}`">
            {{ hit.similarity.toFixed(3) }}
          </span>
        </button>

        <pre v-if="expanded === index" class="hit__body">{{ hit.content }}</pre>
      </div>
    </div>
  </div>
</template>

<style scoped>
.source-panel {
  margin-top: 12px;
  padding: 12px 14px;
  background: var(--bg-subtle);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
}

.source-panel__files {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.source-panel__hits {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed var(--border-default);
}

.source-panel__caption {
  margin-right: 4px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--text-tertiary);
}

.file-chip {
  padding: 2px 8px;
  font-size: 11.5px;
  font-family: var(--font-mono);
  color: var(--brand-700);
  background: var(--brand-50);
  border: 1px solid var(--brand-100);
  border-radius: 999px;
}

.hit {
  margin-top: 4px;
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  overflow: hidden;
}

.hit__head {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 7px 10px;
  border: none;
  background: transparent;
  font-family: inherit;
  font-size: 12px;
  color: var(--text-secondary);
  text-align: left;
  cursor: pointer;
}

.hit__head:hover {
  background: var(--bg-subtle);
}

.hit__caret {
  display: block;
  flex-shrink: 0;
  color: var(--text-tertiary);
  transition: transform 0.15s ease;
}

.hit__caret--open {
  transform: rotate(90deg);
}

.hit__name {
  font-family: var(--font-mono);
  font-size: 11.5px;
  color: var(--text-primary);
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.hit__index {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--text-tertiary);
}

.hit__bar {
  flex: 1;
  min-width: 40px;
  height: 4px;
  background: var(--border-subtle);
  border-radius: 999px;
  overflow: hidden;
}

.hit__bar-fill {
  display: block;
  height: 100%;
  border-radius: 999px;
}

.hit__bar-fill--high {
  background: #10b981;
}
.hit__bar-fill--mid {
  background: #f59e0b;
}
.hit__bar-fill--low {
  background: #d4d4d8;
}

.hit__score {
  flex-shrink: 0;
  font-family: var(--font-mono);
  font-size: 11.5px;
  font-variant-numeric: tabular-nums;
}

.hit__score--high {
  color: #059669;
}
.hit__score--mid {
  color: #b45309;
}
.hit__score--low {
  color: var(--text-tertiary);
}

.hit__body {
  margin: 0;
  padding: 10px 12px;
  max-height: 260px;
  overflow: auto;
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.65;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--text-secondary);
  background: var(--bg-subtle);
  border-top: 1px solid var(--border-subtle);
}
</style>
