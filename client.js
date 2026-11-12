// DSH owns React, form permissions, persistence and revision checks.
window.__ModuleLoader__.load({
  id: '@deepseek-ai/dsh-functional-logic-completion',
  factory(require) {
    const React = require('react'), h = React.createElement;
    const fields = [{"key": "pythonPath", "type": "text", "hint": "pythonHint"}, {"key": "maxIterations", "type": "number", "hint": "iterationsHint", "min": 1, "max": 20, "fallback": 5}, {"key": "maxConcurrent", "type": "number", "hint": "concurrentHint", "min": 1, "max": 16, "fallback": 1}];
    const words = {
      zh: {title: '运行环境与任务配置', intro: '路径均指 DSH 服务端。默认配置通常无需修改。',
        pythonPath: 'Python 解释器', pythonHint: '留空使用本插件的 .venv；其他环境请填写解释器绝对路径。',
        javaPath: 'Java 可执行文件', javaHint: '默认 java，也可填写服务端 Java 21 的绝对路径。',
        plantumlJarPath: 'PlantUML JAR', jarHint: '留空使用随包 tools/plantuml.jar。',
        maxIterations: '最大检查轮次', iterationsHint: '1～20，默认 5。',
        maxConcurrent: '并发任务上限', concurrentHint: '1～16，默认 1。',
        functionTreeJsonMode: '功能树原生 JSON 模式', jsonHint: '需在 DSH 选择支持 JSON 输出的 Chat Completions 连接；不兼容时明确报错，不回退。关闭时仍会校验并有限重试。',
        save: '保存配置', discard: '放弃修改', saving: '正在保存…', saved: '已保存，无需重启；仅影响新任务，运行中的任务保持原配置。',
        loading: '正在读取配置…', unavailable: '请启用本插件及 DSH 原生设置服务。', readOnly: '当前连接没有保存配置的权限。',
        conflict: '配置已在其他页面修改，请放弃修改后重新填写。', invalid: '请检查轮次、并发范围及路径。Java 不能为空。',
        failed: '保存失败，请检查服务端提示。', dirty: '有未保存的修改', timeout: '整体任务与单次模型请求时限，请在软件工厂 Runtime 插件配置页调整。无需填写 API Key 或编辑配置文件。'},
      en: {title: 'Execution settings', intro: 'Paths refer to the DSH server. Defaults usually suffice.',
        pythonPath: 'Python executable', pythonHint: 'Leave blank for this plugin’s .venv, or enter an absolute executable path.',
        javaPath: 'Java executable', javaHint: 'Default: java. An absolute Java 21 executable path is also accepted.',
        plantumlJarPath: 'PlantUML JAR', jarHint: 'Leave blank for the bundled tools/plantuml.jar.',
        maxIterations: 'Maximum iterations', iterationsHint: '1–20. Default: 5.', maxConcurrent: 'Concurrent tasks', concurrentHint: '1–16. Default: 1.',
        functionTreeJsonMode: 'Native JSON mode for the function tree', jsonHint: 'Requires a JSON-capable Chat Completions connection selected in DSH. Unsupported connections fail explicitly. Validation and bounded retries also apply when disabled.',
        save: 'Save settings', discard: 'Discard changes', saving: 'Saving…', saved: 'Saved without restarting. New tasks use these values; running tasks retain their settings.',
        loading: 'Loading settings…', unavailable: 'Enable this plugin and native DSH settings.', readOnly: 'This connection cannot save settings.',
        conflict: 'Settings changed elsewhere. Discard and edit again.', invalid: 'Check iteration limits, concurrency and paths. Java cannot be empty.',
        failed: 'Could not save. Check the server message.', dirty: 'Unsaved changes', timeout: 'Set task and model request timeouts on the Runtime settings page. No API key or configuration file editing is needed.'},
    };
    const values = value => Object.fromEntries(fields.map(f => [f.key, f.type === 'checkbox' ? Boolean(value[f.key]) : String(value[f.key] ?? f.fallback ?? '')]));
    function Configuration({scope, t}) {
      const observer = React.useMemo(() => ({subscribe: fn => scope.subscribe(fn), get: () => scope.getSnapshot()}), [scope]);
      const state = React.useSyncExternalStore(observer.subscribe, observer.get, observer.get);
      const [draft, setDraft] = React.useState(null), [baseline, setBaseline] = React.useState(null), [revision, setRevision] = React.useState();
      const [saving, setSaving] = React.useState(false), [notice, setNotice] = React.useState(''), [error, setError] = React.useState('');
      const id = React.useId(), dirty = draft !== null && JSON.stringify(draft) !== JSON.stringify(baseline), conflict = dirty && revision !== state.revision;
      React.useEffect(() => {
        if (state.status === 'ready' && state.value && !dirty && !saving) {const next = values(state.value); setDraft(next); setBaseline(next); setRevision(state.revision);}
      }, [state.status, state.value, state.revision, dirty, saving]);
      const disabled = saving || !state.writable || state.status !== 'ready';
      function discard() {const next = values(state.value); setDraft(next); setBaseline(next); setRevision(state.revision); setNotice(''); setError('');}
      async function save(event) {
        event.preventDefault(); if (disabled || !dirty || conflict) return;
        const ops = [];
        for (const field of fields) {
          const value = field.type === 'number' ? Number(draft[field.key]) : field.type === 'checkbox' ? draft[field.key] : draft[field.key].trim();
          if (field.type === 'number' && (!String(draft[field.key]).trim() || !Number.isInteger(value) || value < field.min || value > field.max)
              || field.key === 'javaPath' && !value) {setError(t('invalid')); return;}
          ops.push({op: 'set', path: [field.key], value});
        }
        setSaving(true); setError(''); setNotice('');
        try {
          const accepted = await scope.mutate(ops, revision);
          if (accepted) {const current = scope.getSnapshot(), next = values(current.value); setDraft(next); setBaseline(next); setRevision(current.revision); setNotice(t('saved'));}
          else setError(t(scope.getSnapshot().revision !== revision ? 'conflict' : 'failed'));
        } catch {setError(t('failed'));} finally {setSaving(false);}
      }
      return h('form', {className: 'req-settings', onSubmit: save, noValidate: true},
        h('style', null, '.req-settings{display:flex;flex-direction:column;gap:18px;color:var(--dsw-alias-label-primary)}.req-settings h4{margin:0}.req-settings p{font-size:13px;color:var(--dsw-alias-label-secondary);margin:6px 0}.req-settings label{display:block;margin-bottom:6px}.req-settings input:not([type=checkbox]){box-sizing:border-box;width:100%;padding:10px;border:1px solid var(--dsw-alias-border-l3);border-radius:8px;background:var(--dsw-alias-bg-layer-3);color:inherit;font:inherit}.req-settings footer{display:flex;gap:12px}.req-settings button{padding:8px 14px;border:1px solid var(--dsw-alias-border-l3);border-radius:8px;background:var(--dsw-alias-bg-layer-3);color:inherit;cursor:pointer}.req-settings button:disabled{opacity:.4;cursor:default}.req-settings [role=alert]{color:var(--dsw-alias-label-error)}'),
        h('header', null, h('h4', null, t('title')), h('p', null, t('intro'))),
        state.status !== 'ready' || !draft ? h('p', {role: 'status'}, t(state.status === 'loading' ? 'loading' : 'unavailable')) : h(React.Fragment, null,
          !state.writable && h('p', {role: 'status'}, t('readOnly')),
          ...fields.map(field => h('div', {key: field.key}, h('label', {htmlFor: id + field.key}, t(field.key)),
            h('input', {id: id + field.key, name: field.key, type: field.type, disabled, min: field.min, max: field.max,
              ...(field.type === 'checkbox' ? {checked: draft[field.key]} : {value: draft[field.key]}),
              'aria-describedby': id + field.key + '-hint', onChange: e => {setDraft({...draft, [field.key]: field.type === 'checkbox' ? e.target.checked : e.target.value}); setError(''); setNotice('');}}),
            h('p', {id: id + field.key + '-hint'}, t(field.hint)))),
          h('p', null, t('timeout')), (error || conflict) && h('p', {role: 'alert'}, error || t('conflict')),
          h('footer', null, h('button', {type: 'submit', disabled: disabled || !dirty || conflict}, t(saving ? 'saving' : 'save')),
            h('button', {type: 'button', disabled: saving || !dirty, onClick: discard}, t('discard'))),
          h('p', {role: 'status'}, notice || (dirty ? t('dirty') : ''))));
    }
    return {inject: ['slots', 'locale', 'configForms'], apply(ctx) {
      ctx.effect(() => ctx.locale.register('reqCompletionV20Settings', words));
      const scope = ctx.configForms.get('functional-logic-completion');
      ctx.slots.inject('plugins.row.config', () => ctx.slots.register({name: 'plugins.row.config',
        key: '@deepseek-ai/dsh-functional-logic-completion#functional-logic-completion', locale: 'reqCompletionV20Settings', inject: () => ({scope})}, Configuration));
    }};
  },
});
