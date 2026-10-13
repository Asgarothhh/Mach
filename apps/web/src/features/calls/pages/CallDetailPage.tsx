import { useCallback, useEffect, useState } from 'react';
import { ArrowLeft, Clock3, FileText, Headphones, History, MessageSquare, PencilLine, Save, ShieldCheck, UserRound, X } from 'lucide-react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { SectionHeading } from '../../../shared/components/SectionHeading';
import { StatusBadge } from '../../../shared/components/StatusBadge';
import { env } from '../../../shared/config/env';
import { useTenant } from '../../tenant/model/TenantContext';
import type { CallDetail, TranscriptTurn } from '../../../shared/types/track1';
import { correctCallTranscript, getCallDetail } from '../services/calls.service';

function RouteIcon({ decision }: { decision: string }) {
  if (decision === 'chat_offer') return <MessageSquare size={16} />;
  if (decision === 'human_handoff') return <UserRound size={16} />;
  return <Headphones size={16} />;
}

export function CallDetailPage() {
  const { callId = '' } = useParams();
  const location = useLocation();
  const inAdmin = location.pathname.startsWith('/admin');
  const historyHref = inAdmin ? '/admin/calls' : '/calls';
  const { tenantId } = useTenant();
  const [detail, setDetail] = useState<CallDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [draftText, setDraftText] = useState('');
  const [reason, setReason] = useState('Исправление по результатам ручной проверки');
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const canEditInCurrentMode = env.demoMode || detail?.permissions?.can_correct_transcript === true; // Production editing is enabled only by a backend-granted permission.
  const canViewOriginal = env.demoMode || detail?.permissions?.can_view_original === true; // Original ASR revisions are protected separately from masked text.

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try { setDetail(await getCallDetail(callId, tenantId, inAdmin ? 'admin' : 'tenant')); }
    catch (cause) { setLoadError(cause instanceof Error ? cause.message : 'Не удалось загрузить звонок.'); }
    finally { setLoading(false); }
  }, [callId, tenantId, inAdmin]);

  useEffect(() => { void load(); }, [load]);

  function beginEdit(turn: TranscriptTurn) {
    setEditing(turn.turn_id);
    setDraftText(turn.text);
    setReason('Исправление по результатам ручной проверки');
    setNotice(null);
  }

  async function saveCorrection(turn: TranscriptTurn) {
    if (!draftText.trim()) { setNotice('Исправленный текст не может быть пустым.'); return; }
    setSaving(true); setNotice(null);
    try {
      const updated = await correctCallTranscript(detail?.call.call_id ?? callId, callId, tenantId, { turn_id: turn.turn_id, corrected_text: draftText.trim(), reason: reason.trim(), expected_revision: detail?.transcript_revision ?? 'unknown' }, inAdmin ? 'admin' : 'tenant');
      if (updated) setDetail(updated);
      setEditing(null);
      setNotice(env.demoMode ? 'Демо-коррекция сохранена с исходным текстом и новой ревизией. В production запись должен подтвердить backend и audit log.' : 'Коррекция отправлена в backend. Проверьте новую ревизию и audit event.');
    } catch (cause) {
      setNotice(cause instanceof Error ? cause.message : 'Не удалось сохранить корректировку.');
    } finally { setSaving(false); }
  }

  if (loading) return <div className="track-page"><div className="track-empty-state"><span className="loading-dot" />Загружаем детали звонка…</div></div>;
  if (loadError || !detail) return <div className="track-page"><SectionHeading eyebrow="CALL DETAIL" title="Звонок не найден" description={loadError ?? 'Запись отсутствует или недоступна текущей роли.'} action={<Link to={historyHref} className="button button--secondary button--small"><ArrowLeft size={15} /> К истории</Link>} /><div className="track-info-panel"><ShieldCheck size={20} /><div><strong>Доступ контролирует backend</strong><p>Не пытайтесь открывать чужие call ID. Сервер обязан проверять tenant ownership независимо от случайности идентификатора.</p></div></div></div>;

  const { call, turns, routing_events: routingEvents, sources } = detail;
  return (
    <div className="track-page">
      <SectionHeading eyebrow="CALL DETAIL · TRANSCRIPT AUDIT" title="Детали звонка" description={`${call.call_id} · ${new Date(call.created_at).toLocaleString('ru-RU')} · ${call.caller_alias}`} action={<Link to={historyHref} className="button button--secondary button--small"><ArrowLeft size={15} /> К истории звонков</Link>} />
      {env.demoMode && <div className="track-demo-banner"><span className="track-demo-dot" /><div><strong>Синтетическая запись</strong><p>Все реплики и события в этом вызове — примеры UI, не запись реального клиента.</p></div><StatusBadge tone="demo">DEMO</StatusBadge></div>}
      {notice && <div className={`track-inline-message ${notice.includes('не может') || notice.includes('Не удалось') ? 'is-warning' : 'is-success'}`} role="status">{notice}</div>}

      <div className="track-call-summary-grid">
        <div className="track-summary-card"><span>Статус</span><strong>{call.status === 'completed' ? 'Завершён' : call.status === 'active' ? 'Активен' : call.status === 'handoff' ? 'Передан' : call.status === 'degraded' ? 'Деградация' : 'Ошибка'}</strong><small>{call.channel === 'telephone' ? 'Входящий телефон' : call.channel === 'test_call' ? 'Mock/test call' : 'Browser test'}</small></div>
        <div className="track-summary-card"><span>Длительность</span><strong>{call.duration_seconds == null ? '—' : `${Math.floor(call.duration_seconds / 60)}:${String(call.duration_seconds % 60).padStart(2, '0')}`}</strong><small>{call.turn_count} ход(а)</small></div>
        <div className="track-summary-card"><span>Routing decision</span><strong className="track-summary-card__route"><RouteIcon decision={call.route_decision} />{call.route_decision === 'voice' ? 'Голос' : call.route_decision === 'chat_offer' ? 'Предложен чат' : call.route_decision === 'human_handoff' ? 'Human handoff' : 'Fallback'}</strong><small>Согласие: {call.consent_state === 'accepted' ? 'принято' : call.consent_state === 'declined' ? 'отклонено' : call.consent_state === 'pending' ? 'ожидание' : 'demo'}</small></div>
        <div className="track-summary-card"><span>Endpoint → first audio</span><strong>{call.ttfa_ms == null ? '—' : `${call.ttfa_ms} мс`}</strong><small>Показатель записи; не SLA</small></div>
      </div>

      <div className="track-call-detail-grid">
        <section className="track-panel">
          <div className="track-panel__heading"><div><span className="track-eyebrow">TRANSCRIPT · {detail.transcript_revision}</span><h2>Транскрипт разговора</h2></div><span className="track-tenant-lock"><History size={13} /> Versioned edit</span></div>
          <div className="track-info-panel track-info-panel--privacy"><ShieldCheck size={19} /><div><strong>Оригинальная ревизия сохраняется</strong><p>Коррекция не должна перезаписывать исходную ASR-версию. В production нужны роль transcript_editor, diff, автор, причина и audit event.</p></div></div>
          {!canEditInCurrentMode && <div className="track-inline-message is-warning">Редактирование выключено, пока frontend не получает подтверждённое право transcript_editor от backend.</div>}
          <div className="track-transcript-list">{turns.map((turn) => <article className={`track-transcript-turn track-transcript-turn--${turn.role}`} key={turn.turn_id}>
            <div className="track-transcript-turn__meta"><strong>{turn.role === 'caller' ? 'Звонящий' : turn.role === 'agent' ? 'ИИ-агент' : 'Системное событие'}</strong><span>{new Date(turn.started_at).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span><span className={`track-transcript-state track-transcript-state--${turn.status}`}>{turn.status === 'interim' ? 'Промежуточный' : turn.status === 'corrected' ? 'Исправлен' : 'Final'}</span>{turn.confidence !== undefined && <span>confidence {Math.round(turn.confidence * 100)}%</span>}</div>
            {editing === turn.turn_id ? <div className="track-edit-form"><label className="track-field"><span>Исправленный текст</span><textarea rows={4} value={draftText} onChange={(event) => setDraftText(event.target.value)} /></label><label className="track-field"><span>Причина исправления</span><input value={reason} onChange={(event) => setReason(event.target.value)} maxLength={500} /></label><div className="track-panel__actions"><button className="button button--secondary button--small" onClick={() => setEditing(null)} disabled={saving}><X size={14} /> Отмена</button><button className="button button--primary button--small" onClick={() => void saveCorrection(turn)} disabled={saving}><Save size={14} /> {saving ? 'Сохраняем…' : 'Сохранить ревизию'}</button></div></div> : <><p className="track-transcript-turn__text">{turn.text}</p>{turn.original_text && <div className="track-correction-diff">{canViewOriginal ? <><span>Original revision</span><p>{turn.original_text}</p></> : <p>Исходная ревизия скрыта: у вашей роли нет права просмотра оригинального текста.</p>}<span>Исправленная версия</span><p>{turn.text}</p><span>Причина</span><p>{turn.correction_reason ?? 'Причина не указана'}</p>{turn.correction_audit && <><span>Аудит</span><p><code>{turn.correction_audit.audit_event_id}</code> · {turn.correction_audit.actor_id} · {new Date(turn.correction_audit.corrected_at).toLocaleString('ru-RU')}</p></>}</div>}{canEditInCurrentMode && turn.role === 'caller' && <button className="track-text-button" onClick={() => beginEdit(turn)}><PencilLine size={14} /> Исправить транскрипт</button>}</>}
            {turn.citations?.length ? <div className="track-turn-sources">{turn.citations.map((source) => <a key={source.source_id} href={source.url} target="_blank" rel="noopener noreferrer"><FileText size={13} /> {source.title}</a>)}</div> : null}
          </article>)}</div>
        </section>

        <div className="track-side-stack">
          <section className="track-panel"><div className="track-panel__heading"><div><span className="track-eyebrow">ROUTING AUDIT</span><h2>Решения маршрутизатора</h2></div></div><div className="track-timeline">{routingEvents.map((event) => <div className="track-timeline-item" key={event.event_id}><span className="track-timeline-item__dot" /><div className="track-timeline-item__body"><small>{new Date(event.created_at).toLocaleTimeString('ru-RU')}</small><strong>{event.decision === 'voice' ? 'Голосовой ответ' : event.decision === 'chat_offer' ? 'Предложение чата' : event.decision === 'human_handoff' ? 'Перевод человеку' : 'Безопасный fallback'}</strong><p>{event.reason}</p><span className="track-timeline-item__meta">{event.policy_revision} · consent: {event.consent_state}</span>{event.outcome && <div className="track-outcome">{event.outcome}</div>}</div></div>)}</div></section>
          <section className="track-panel"><div className="track-panel__heading"><div><span className="track-eyebrow">TENANT EVIDENCE</span><h2>Источники ответа</h2></div><StatusBadge tone="neutral">{sources.length}</StatusBadge></div>{sources.length === 0 ? <div className="track-empty-state">Для этого вызова нет сохранённых источников.</div> : <div className="track-source-list">{sources.map((source) => <a className="track-source-item" href={source.url} target="_blank" rel="noopener noreferrer" key={source.source_id}><span className="track-source-item__icon"><FileText size={16} /></span><span><strong>{source.title}</strong><small>{source.url}</small><small>{source.revision_id} · {source.approved ? 'approved demo fixture' : 'not approved'}</small>{source.excerpt && <p>{source.excerpt}</p>}</span></a>)}</div>}<p className="track-panel-footnote">Необходимо подтверждать tenant_id и одобрение источника на backend; ссылки в UI не являются подтверждением доступа.</p></section>
          <section className="track-panel"><div className="track-panel__heading"><div><span className="track-eyebrow">PRIVACY</span><h2>Согласие и хранение</h2></div><ShieldCheck size={20} /></div><div className="track-policy-rows"><div><span>Состояние уведомления</span><strong>{call.consent_state === 'accepted' ? 'Принято' : call.consent_state === 'declined' ? 'Отказ' : call.consent_state === 'pending' ? 'Ожидает' : 'Тестовое демо'}</strong></div><div><span>Сырое аудио сохранено</span><strong>{detail.audio_recorded ? 'Да · проверяйте policy и retention' : 'Нет'}</strong></div><div><span>Caller identity</span><strong>Masked / alias</strong></div><div><span>Call ID</span><code>{call.call_id}</code></div></div></section>
        </div>
      </div>
      <div className="track-page-footnote"><Clock3 size={14} /> Детали — это UI-представление звонка. Полномочия на чтение/коррекцию и аудит обеспечиваются сервером, не React-маршрутом.</div>
    </div>
  );
}
