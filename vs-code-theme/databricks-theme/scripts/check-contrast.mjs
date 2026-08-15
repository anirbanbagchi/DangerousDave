#!/usr/bin/env node
/**
 * Databricks theme — accessibility check.
 *
 * Parses both theme files and reports WCAG 2.1 contrast ratios for every
 * foreground/background pair the theme is responsible for.
 *
 *   node scripts/check-contrast.mjs          # full table
 *   node scripts/check-contrast.mjs --fail   # only the failures
 *
 * Thresholds
 *   text  >= 4.5:1   normal-weight text, including comments, dimmed text,
 *                    syntax tokens and terminal ANSI colours
 *   ui    >= 3.0:1   borders that carry meaning, focus rings, indicators,
 *                    status/gutter icons, chart series
 *
 * Also validates that both files parse as JSON, contain no duplicate keys, and
 * declare exactly the same set of workbench colour keys as each other.
 *
 * No dependencies; Node 18+.
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const ONLY_FAILURES = process.argv.includes('--fail');

const TEXT = 4.5;
const UI = 3.0;

/* ------------------------------------------------------------------ colour */

function parseHex(value) {
  if (typeof value !== 'string' || !/^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$/.test(value)) {
    throw new Error(`not a hex colour: ${JSON.stringify(value)}`);
  }
  const hex = value.slice(1);
  return {
    r: parseInt(hex.slice(0, 2), 16),
    g: parseInt(hex.slice(2, 4), 16),
    b: parseInt(hex.slice(4, 6), 16),
    a: hex.length === 8 ? parseInt(hex.slice(6, 8), 16) / 255 : 1
  };
}

/** Flatten a translucent colour onto an opaque one (simple source-over). */
function composite(top, bottom) {
  if (top.a >= 1) return { ...top, a: 1 };
  return {
    r: top.r * top.a + bottom.r * (1 - top.a),
    g: top.g * top.a + bottom.g * (1 - top.a),
    b: top.b * top.a + bottom.b * (1 - top.a),
    a: 1
  };
}

function relativeLuminance({ r, g, b }) {
  const channel = (v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

function contrast(fg, bg) {
  const a = relativeLuminance(fg);
  const b = relativeLuminance(bg);
  const [hi, lo] = a > b ? [a, b] : [b, a];
  return (hi + 0.05) / (lo + 0.05);
}

/* ----------------------------------------------------------- duplicate keys */

/**
 * Minimal JSON scanner that reports keys defined more than once inside the
 * same object. JSON.parse silently keeps the last one, so this has to be done
 * against the raw text.
 */
function duplicateKeys(text) {
  const dups = [];
  const stack = [];
  let i = 0;

  const readString = () => {
    let out = '';
    i++; // opening quote
    while (i < text.length) {
      const ch = text[i];
      if (ch === '\\') {
        out += text[i] + text[i + 1];
        i += 2;
        continue;
      }
      if (ch === '"') {
        i++;
        return out;
      }
      out += ch;
      i++;
    }
    return out;
  };

  while (i < text.length) {
    const ch = text[i];
    if (ch === '"') {
      const start = i;
      const str = readString();
      let j = i;
      while (j < text.length && /\s/.test(text[j])) j++;
      const top = stack[stack.length - 1];
      if (text[j] === ':' && top && top.type === 'object') {
        if (top.keys.has(str)) {
          const line = text.slice(0, start).split('\n').length;
          dups.push({ key: str, line });
        }
        top.keys.add(str);
      }
      continue;
    }
    if (ch === '{') stack.push({ type: 'object', keys: new Set() });
    else if (ch === '[') stack.push({ type: 'array' });
    else if (ch === '}' || ch === ']') stack.pop();
    i++;
  }
  return dups;
}

/* ------------------------------------------------------------------- checks */

/**
 * Pair definitions. `bg` may be translucent, in which case it is flattened
 * onto `base` (defaults to the variant's editor background) first.
 */
const TEXT_PAIRS = [
  ['foreground', 'editor.background'],
  ['descriptionForeground', 'editor.background'],
  ['disabledForeground', 'editor.background'],
  ['errorForeground', 'editor.background'],
  ['textLink.foreground', 'editor.background'],
  ['textPreformat.foreground', 'textPreformat.background'],

  ['editor.foreground', 'editor.background'],
  ['editorLineNumber.foreground', 'editor.background'],
  ['editorLineNumber.activeForeground', 'editor.background'],
  ['editorCodeLens.foreground', 'editor.background'],
  ['editorGhostText.foreground', 'editor.background'],
  ['editorInlayHint.foreground', 'editorInlayHint.background'],
  ['editorError.foreground', 'editor.background'],
  ['editorWarning.foreground', 'editor.background'],
  ['editorInfo.foreground', 'editor.background'],
  ['editorHint.foreground', 'editor.background'],
  ['editor.foldPlaceholderForeground', 'editor.background'],

  ['editorBracketHighlight.foreground1', 'editor.background'],
  ['editorBracketHighlight.foreground2', 'editor.background'],
  ['editorBracketHighlight.foreground3', 'editor.background'],
  ['editorBracketHighlight.foreground4', 'editor.background'],
  ['editorBracketHighlight.foreground5', 'editor.background'],
  ['editorBracketHighlight.foreground6', 'editor.background'],
  ['editorBracketHighlight.unexpectedBracket.foreground', 'editor.background'],

  ['editorWidget.foreground', 'editorWidget.background'],
  ['editorSuggestWidget.foreground', 'editorSuggestWidget.background'],
  ['editorSuggestWidget.highlightForeground', 'editorSuggestWidget.background'],
  ['editorSuggestWidget.selectedForeground', 'editorSuggestWidget.selectedBackground'],
  ['editorSuggestWidgetStatus.foreground', 'editorSuggestWidget.background'],
  ['editorHoverWidget.foreground', 'editorHoverWidget.background'],

  ['activityBar.foreground', 'activityBar.background'],
  ['activityBar.inactiveForeground', 'activityBar.background'],
  ['activityBarBadge.foreground', 'activityBarBadge.background'],

  ['sideBar.foreground', 'sideBar.background'],
  ['sideBarTitle.foreground', 'sideBar.background'],
  ['sideBarSectionHeader.foreground', 'sideBarSectionHeader.background'],

  ['list.activeSelectionForeground', 'list.activeSelectionBackground'],
  ['list.inactiveSelectionForeground', 'list.inactiveSelectionBackground'],
  ['list.hoverForeground', 'list.hoverBackground', 'sideBar.background'],
  ['list.highlightForeground', 'list.activeSelectionBackground'],
  ['list.deemphasizedForeground', 'sideBar.background'],
  ['list.invalidItemForeground', 'sideBar.background'],
  ['list.errorForeground', 'sideBar.background'],
  ['list.warningForeground', 'sideBar.background'],

  ['tab.activeForeground', 'tab.activeBackground'],
  ['tab.inactiveForeground', 'tab.inactiveBackground'],
  ['tab.unfocusedActiveForeground', 'tab.unfocusedActiveBackground'],
  ['tab.unfocusedInactiveForeground', 'tab.unfocusedInactiveBackground'],
  ['breadcrumb.foreground', 'breadcrumb.background'],
  ['breadcrumb.focusForeground', 'breadcrumb.background'],
  ['breadcrumb.activeSelectionForeground', 'breadcrumb.background'],

  ['statusBar.foreground', 'statusBar.background'],
  ['statusBar.debuggingForeground', 'statusBar.debuggingBackground'],
  ['statusBar.noFolderForeground', 'statusBar.noFolderBackground'],
  ['statusBar.offlineForeground', 'statusBar.offlineBackground'],
  ['statusBarItem.prominentForeground', 'statusBarItem.prominentBackground'],
  ['statusBarItem.errorForeground', 'statusBarItem.errorBackground'],
  ['statusBarItem.warningForeground', 'statusBarItem.warningBackground'],
  ['statusBarItem.remoteForeground', 'statusBarItem.remoteBackground'],
  ['statusBarItem.offlineForeground', 'statusBarItem.offlineBackground'],
  ['statusBarItem.settingsProfilesForeground', 'statusBarItem.settingsProfilesBackground'],

  ['titleBar.activeForeground', 'titleBar.activeBackground'],
  ['titleBar.inactiveForeground', 'titleBar.inactiveBackground'],
  ['menu.foreground', 'menu.background'],
  ['menu.selectionForeground', 'menu.selectionBackground'],
  ['menubar.selectionForeground', 'menubar.selectionBackground'],
  ['commandCenter.foreground', 'commandCenter.background'],
  ['commandCenter.inactiveForeground', 'commandCenter.background'],
  ['commandCenter.activeForeground', 'commandCenter.activeBackground'],
  ['banner.foreground', 'banner.background'],

  ['panelTitle.activeForeground', 'panel.background'],
  ['panelTitle.inactiveForeground', 'panel.background'],
  ['panelSectionHeader.foreground', 'panelSectionHeader.background'],
  ['terminal.foreground', 'terminal.background'],

  ['debugConsole.infoForeground', 'panel.background'],
  ['debugConsole.warningForeground', 'panel.background'],
  ['debugConsole.errorForeground', 'panel.background'],
  ['debugConsole.sourceForeground', 'panel.background'],
  ['debugTokenExpression.name', 'editor.background'],
  ['debugTokenExpression.value', 'editor.background'],
  ['debugTokenExpression.string', 'editor.background'],
  ['debugTokenExpression.boolean', 'editor.background'],
  ['debugTokenExpression.number', 'editor.background'],
  ['debugTokenExpression.error', 'editor.background'],
  ['debugView.stateLabelForeground', 'debugView.stateLabelBackground'],

  ['input.foreground', 'input.background'],
  ['input.placeholderForeground', 'input.background'],
  ['inputOption.activeForeground', 'inputOption.activeBackground'],
  ['inputValidation.errorForeground', 'inputValidation.errorBackground'],
  ['inputValidation.warningForeground', 'inputValidation.warningBackground'],
  ['inputValidation.infoForeground', 'inputValidation.infoBackground'],
  ['dropdown.foreground', 'dropdown.background'],
  ['button.foreground', 'button.background'],
  ['button.foreground', 'button.hoverBackground'],
  ['button.secondaryForeground', 'button.secondaryBackground'],
  ['button.secondaryForeground', 'button.secondaryHoverBackground'],
  ['checkbox.foreground', 'checkbox.background'],
  ['radio.activeForeground', 'radio.activeBackground'],
  ['badge.foreground', 'badge.background'],
  ['profileBadge.foreground', 'profileBadge.background'],
  ['keybindingLabel.foreground', 'keybindingLabel.background'],
  ['extensionButton.prominentForeground', 'extensionButton.prominentBackground'],
  ['extensionBadge.remoteForeground', 'extensionBadge.remoteBackground'],

  ['notifications.foreground', 'notifications.background'],
  ['notificationLink.foreground', 'notifications.background'],
  ['notificationCenterHeader.foreground', 'notificationCenterHeader.background'],
  ['quickInput.foreground', 'quickInput.background'],
  ['quickInputList.focusForeground', 'quickInputList.focusBackground'],
  ['pickerGroup.foreground', 'quickInput.background'],
  ['search.resultsInfoForeground', 'sideBar.background'],

  ['peekViewResult.fileForeground', 'peekViewResult.background'],
  ['peekViewResult.lineForeground', 'peekViewResult.background'],
  ['peekViewResult.selectionForeground', 'peekViewResult.selectionBackground'],
  ['peekViewTitleLabel.foreground', 'peekViewTitle.background'],
  ['peekViewTitleDescription.foreground', 'peekViewTitle.background'],
  ['diffEditor.unchangedRegionForeground', 'diffEditor.unchangedRegionBackground'],

  ['gitDecoration.addedResourceForeground', 'sideBar.background'],
  ['gitDecoration.modifiedResourceForeground', 'sideBar.background'],
  ['gitDecoration.deletedResourceForeground', 'sideBar.background'],
  ['gitDecoration.renamedResourceForeground', 'sideBar.background'],
  ['gitDecoration.untrackedResourceForeground', 'sideBar.background'],
  ['gitDecoration.ignoredResourceForeground', 'sideBar.background'],
  ['gitDecoration.conflictingResourceForeground', 'sideBar.background'],
  ['gitDecoration.stageModifiedResourceForeground', 'sideBar.background'],
  ['gitDecoration.stageDeletedResourceForeground', 'sideBar.background'],
  ['gitDecoration.submoduleResourceForeground', 'sideBar.background'],

  ['settings.headerForeground', 'editor.background'],
  ['settings.dropdownForeground', 'settings.dropdownBackground'],
  ['settings.textInputForeground', 'settings.textInputBackground'],
  ['settings.numberInputForeground', 'settings.numberInputBackground'],
  ['settings.checkboxForeground', 'settings.checkboxBackground'],
  ['charts.foreground', 'editor.background']
];

const UI_PAIRS = [
  ['focusBorder', 'editor.background'],
  ['focusBorder', 'sideBar.background'],
  ['focusBorder', 'editorWidget.background'],
  ['contrastActiveBorder', 'editor.background'],
  ['editorCursor.foreground', 'editor.background'],
  ['terminalCursor.foreground', 'terminal.background'],
  ['editorMultiCursor.secondary.foreground', 'editor.background'],
  ['editorIndentGuide.activeBackground1', 'editor.background'],
  ['editorLineNumber.dimmedForeground', 'editor.background'],
  ['editorBracketMatch.border', 'editor.background'],
  ['editorGutter.addedBackground', 'editor.background'],
  ['editorGutter.modifiedBackground', 'editor.background'],
  ['editorGutter.deletedBackground', 'editor.background'],
  ['editorGutter.foldingControlForeground', 'editor.background'],
  ['editorGutter.commentRangeForeground', 'editor.background'],
  ['minimapGutter.addedBackground', 'editor.background'],
  ['minimapGutter.modifiedBackground', 'editor.background'],
  ['minimapGutter.deletedBackground', 'editor.background'],
  ['minimap.errorHighlight', 'editor.background'],
  ['minimap.warningHighlight', 'editor.background'],
  ['minimap.infoHighlight', 'editor.background'],
  ['icon.foreground', 'editor.background'],
  ['sash.hoverBorder', 'editor.background'],
  ['peekView.border', 'editor.background'],
  ['notebook.focusedCellBorder', 'editor.background'],
  ['notebook.cellInsertionIndicator', 'editor.background'],

  ['activityBar.activeBorder', 'activityBar.background'],
  ['activityBarTop.activeBorder', 'activityBarTop.background'],
  ['tab.activeBorderTop', 'tab.activeBackground'],
  ['tab.activeModifiedBorder', 'tab.activeBackground'],
  ['tab.inactiveModifiedBorder', 'tab.inactiveBackground'],
  ['panelTitle.activeBorder', 'panel.background'],
  ['panelInput.border', 'panel.background'],
  ['statusBar.focusBorder', 'statusBar.background'],
  ['statusBarItem.focusBorder', 'statusBar.background'],
  ['progressBar.background', 'editor.background'],
  ['settings.modifiedItemIndicator', 'editor.background'],

  ['list.focusOutline', 'list.activeSelectionBackground'],
  ['list.focusAndSelectionOutline', 'list.activeSelectionBackground'],
  ['list.inactiveFocusOutline', 'list.inactiveSelectionBackground'],
  ['menu.selectionBorder', 'menu.selectionBackground'],
  ['menubar.selectionBorder', 'menubar.selectionBackground'],
  ['listFilterWidget.outline', 'editorWidget.background'],
  ['listFilterWidget.noMatchesOutline', 'editorWidget.background'],

  ['input.border', 'input.background'],
  ['dropdown.border', 'dropdown.background'],
  ['checkbox.border', 'checkbox.background'],
  ['radio.inactiveBorder', 'editor.background'],
  ['settings.textInputBorder', 'settings.textInputBackground'],
  ['settings.numberInputBorder', 'settings.numberInputBackground'],
  ['settings.checkboxBorder', 'settings.checkboxBackground'],
  ['settings.dropdownBorder', 'settings.dropdownBackground'],
  ['searchEditor.textInputBorder', 'input.background'],
  ['inputOption.activeBorder', 'inputOption.activeBackground'],
  ['inputValidation.errorBorder', 'inputValidation.errorBackground'],
  ['inputValidation.warningBorder', 'inputValidation.warningBackground'],
  ['inputValidation.infoBorder', 'inputValidation.infoBackground'],
  ['debugExceptionWidget.border', 'debugExceptionWidget.background'],

  ['notificationsErrorIcon.foreground', 'notifications.background'],
  ['notificationsWarningIcon.foreground', 'notifications.background'],
  ['notificationsInfoIcon.foreground', 'notifications.background'],
  ['problemsErrorIcon.foreground', 'sideBar.background'],
  ['problemsWarningIcon.foreground', 'sideBar.background'],
  ['problemsInfoIcon.foreground', 'sideBar.background'],
  ['editorLightBulb.foreground', 'editor.background'],
  ['editorLightBulbAutoFix.foreground', 'editor.background'],
  ['debugIcon.breakpointForeground', 'editor.background'],
  ['debugIcon.breakpointDisabledForeground', 'editor.background'],
  ['debugIcon.startForeground', 'debugToolBar.background'],
  ['debugIcon.stopForeground', 'debugToolBar.background'],
  ['debugIcon.pauseForeground', 'debugToolBar.background'],
  ['debugIcon.continueForeground', 'debugToolBar.background'],
  ['testing.iconFailed', 'sideBar.background'],
  ['testing.iconPassed', 'sideBar.background'],
  ['testing.iconQueued', 'sideBar.background'],
  ['testing.iconSkipped', 'sideBar.background'],
  ['ports.iconRunningProcessForeground', 'panel.background'],
  ['notebookStatusErrorIcon.foreground', 'editor.background'],
  ['notebookStatusRunningIcon.foreground', 'editor.background'],
  ['notebookStatusSuccessIcon.foreground', 'editor.background'],
  ['extensionIcon.starForeground', 'sideBar.background'],
  ['extensionIcon.verifiedForeground', 'sideBar.background'],
  ['extensionIcon.preReleaseForeground', 'sideBar.background'],
  ['extensionIcon.sponsorForeground', 'sideBar.background'],

  ['mergeEditor.conflict.unhandledFocused.border', 'editor.background'],
  ['mergeEditor.conflict.unhandledUnfocused.border', 'editor.background'],
  ['mergeEditor.conflict.handledFocused.border', 'editor.background'],
  ['mergeEditor.conflict.handledUnfocused.border', 'editor.background'],
  ['diffEditorOverview.insertedForeground', 'editor.background'],
  ['diffEditorOverview.removedForeground', 'editor.background'],

  ['charts.red', 'editor.background'],
  ['charts.blue', 'editor.background'],
  ['charts.yellow', 'editor.background'],
  ['charts.orange', 'editor.background'],
  ['charts.green', 'editor.background'],
  ['charts.purple', 'editor.background'],
  ['welcomePage.progress.foreground', 'welcomePage.background']
];

/**
 * ANSI slots checked against the terminal background. black/brightBlack and
 * white/brightWhite are excluded: those four slots are, by definition, the
 * extremes of the terminal's own palette, and every terminal emulator ships
 * them at low contrast against one end of the background range.
 */
const ANSI_SLOTS = [
  'terminal.ansiRed', 'terminal.ansiGreen', 'terminal.ansiYellow',
  'terminal.ansiBlue', 'terminal.ansiMagenta', 'terminal.ansiCyan',
  'terminal.ansiBrightRed', 'terminal.ansiBrightGreen', 'terminal.ansiBrightYellow',
  'terminal.ansiBrightBlue', 'terminal.ansiBrightMagenta', 'terminal.ansiBrightCyan'
];

/* -------------------------------------------------------------------- runner */

function resolve(theme, key) {
  const value = theme.colors[key];
  if (value === undefined) throw new Error(`missing colour key: ${key}`);
  return parseHex(value);
}

function checkTheme(theme, raw) {
  const rows = [];
  const base = resolve(theme, 'editor.background');

  const add = (group, threshold, label, fgColor, bgColor) => {
    const bg = composite(bgColor, base);
    const fg = composite(fgColor, bg);
    const ratio = contrast(fg, bg);
    rows.push({ group, threshold, label, ratio, pass: ratio + 1e-9 >= threshold });
  };

  for (const [fgKey, bgKey, baseKey] of TEXT_PAIRS) {
    const bgBase = baseKey ? composite(resolve(theme, baseKey), base) : base;
    const bg = composite(resolve(theme, bgKey), bgBase);
    const fg = composite(resolve(theme, fgKey), bg);
    const ratio = contrast(fg, bg);
    rows.push({
      group: 'workbench text',
      threshold: TEXT,
      label: `${fgKey} on ${bgKey}`,
      ratio,
      pass: ratio + 1e-9 >= TEXT
    });
  }

  for (const [fgKey, bgKey] of UI_PAIRS) {
    add('ui / borders / icons', UI, `${fgKey} on ${bgKey}`, resolve(theme, fgKey), resolve(theme, bgKey));
  }

  const terminalBg = composite(resolve(theme, 'terminal.background'), base);
  for (const key of ANSI_SLOTS) {
    add('terminal ansi', TEXT, `${key} on terminal.background`, resolve(theme, key), terminalBg);
  }

  for (const rule of theme.tokenColors) {
    const fg = rule.settings && rule.settings.foreground;
    if (!fg) continue;
    add('syntax (tokenColors)', TEXT, `${rule.name} on editor.background`, parseHex(fg), base);
  }

  for (const [token, style] of Object.entries(theme.semanticTokenColors)) {
    const fg = typeof style === 'string' ? style : style.foreground;
    if (!fg) continue;
    add('syntax (semantic)', TEXT, `${token} on editor.background`, parseHex(fg), base);
  }

  return { rows, dups: duplicateKeys(raw) };
}

function print(name, result) {
  const groups = [...new Set(result.rows.map((r) => r.group))];
  const width = Math.max(...result.rows.map((r) => r.label.length));

  console.log(`\n\x1b[1m${name}\x1b[0m`);
  for (const group of groups) {
    const rows = result.rows
      .filter((r) => r.group === group)
      .filter((r) => !ONLY_FAILURES || !r.pass);
    if (!rows.length) continue;
    const threshold = rows[0].threshold.toFixed(1);
    console.log(`\n  ${group}  (>= ${threshold}:1)`);
    for (const r of rows) {
      const mark = r.pass ? '\x1b[32mPASS\x1b[0m' : '\x1b[31mFAIL\x1b[0m';
      console.log(`    ${mark}  ${r.ratio.toFixed(2).padStart(6)}:1  ${r.label.padEnd(width)}`);
    }
  }

  const failed = result.rows.filter((r) => !r.pass);
  console.log(
    `\n  ${result.rows.length} pairs checked, ${result.rows.length - failed.length} pass, ${failed.length} fail`
  );
  if (result.dups.length) {
    for (const d of result.dups) console.log(`  \x1b[31mduplicate key\x1b[0m "${d.key}" at line ${d.line}`);
  } else {
    console.log('  no duplicate keys');
  }
  return failed.length + result.dups.length;
}

const files = [
  ['Databricks Light', 'themes/databricks-light-color-theme.json'],
  ['Databricks Dark', 'themes/databricks-dark-color-theme.json']
];

let problems = 0;
const keySets = [];

for (const [name, file] of files) {
  const raw = fs.readFileSync(path.join(ROOT, file), 'utf8');
  let theme;
  try {
    theme = JSON.parse(raw);
  } catch (err) {
    console.error(`\n${name}: ${file} does not parse as JSON — ${err.message}`);
    process.exit(1);
  }
  keySets.push({ name, keys: Object.keys(theme.colors) });
  problems += print(name, checkTheme(theme, raw));
}

// Both variants must cover exactly the same workbench keys.
const [a, b] = keySets;
const onlyA = a.keys.filter((k) => !b.keys.includes(k));
const onlyB = b.keys.filter((k) => !a.keys.includes(k));
console.log('\n\x1b[1mVariant parity\x1b[0m');
if (onlyA.length || onlyB.length) {
  problems += onlyA.length + onlyB.length;
  for (const k of onlyA) console.log(`  \x1b[31monly in ${a.name}\x1b[0m: ${k}`);
  for (const k of onlyB) console.log(`  \x1b[31monly in ${b.name}\x1b[0m: ${k}`);
} else {
  console.log(`  both variants define the same ${a.keys.length} workbench colour keys`);
}

console.log(
  problems === 0
    ? '\n\x1b[32mAll checks passed.\x1b[0m'
    : `\n\x1b[31m${problems} problem(s) found.\x1b[0m`
);
process.exit(problems === 0 ? 0 : 1);
