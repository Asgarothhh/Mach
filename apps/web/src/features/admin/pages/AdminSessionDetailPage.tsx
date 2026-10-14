import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { ArrowLeft, Check, Clock3, MessageSquare, PhoneForwarded, RefreshCw, ShieldCheck, Square, UserRound } from 'lucide-react';
import { Link, Navigate, useParams } from 'react-router-dom';
import { SectionHeading } from '../../../shared/components/SectionHeading';
import { StatusBadge } from '../../../shared/components/StatusBadge';
import { env } from '../../../shared/config/env';
import {
  correctBackendTranscript,
  endBackendSession,
  getBackendSession,
  handoffBackendSessionToChat,
  handoffBackendSessionToHuman,
  isTerminalSessionStatus,
  sessionStatusLabels,
  sessionStatusTone,
  type BackendSessionDetail,
  type BackendTurn,
} from '../services/adminSessions.service';

function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('ru-RU');
}

export function AdminSessionDetailPage() {
  if (!env.backendAdminSessions) return <Navigate to="/admin/calls" replace />;
  return <BackendAdminSessionDetailPage />;
}

function BackendAdminSessionDetailPage() {
  const { sessionId = '' } = useParams();
  const [detail, setDetail] = useState<BackendSessionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [chatLink, setChatLink] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [editingTurn, setEditingTurn] = useState<BackendTurn | null>(null);
  const [correctedText, setCorrectedText] = useState('');
  const [correctionReason, setCorrectionReason] = useState('ASR_error');
  const [correctionBusy, setCorrectionBusy] = useState(false);

  const load = useCallback(async () => {
    if (!sessionId) return;
    setLoading(true);
    setError(null);
    try {
      setDetail(await getBackendSession(sessionId));
    } catch (cause) {
      setDetail(null);
      setError(cause instanceof Error ? cause.message : 'Не удалось загрузить сессию.');
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => { void load(); }, [load]);

  async function runAction(action: 'end' | 'human' | 'chat') {
    if (!sessionId) return;
    setBusyAction(action);
    setError(null);
    setActionMessage(null);
    setChatLink(null);
    try {
      if (action === 'end') {
        await endBackendSession(sessionId);
        setActionMessage('Запрос на завершение сессии успешно обработан.');
      } else {
        const response = action === 'human'
          ? await handoffBackendSessionToHuman(sessionId)
          : await handoffBackendSessionToChat(sessionId);
        setActionMessage(response.message);
        setChatLink(response.chat_link ?? null);
      }
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось выполнить действие.');
    } finally {
      setBusyAction(null);
    }
  }

  function startCorrection(turn: BackendTurn) {
    setEditingTurn(turn);
    setCorrectedText(turn.redacted_text ?? '');
    setCorrectionReason('ASR_error');
    setActionMessage(null);
  }

  async function submitCorrection(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!sessionId || !editingTurn || !correctedText.trim() || !correctionReason.trim()) return;
    setCorrectionBusy(true);
    setError(null);
    setActionMessage(null);
    try {
      await correctBackendTranscript(sessionId, {
        turn_id: editingTurn.turn_id,
        corrected_text: correctedText.trim(),
        reason: correctionReason.trim(),
      });
      setEditingTurn(null);
      setActionMessage('Коррекция отправлена. Backend отвечает за сохранение версии и аудит.');
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось исправить транскрипт.');
    } finally {
      setCorrectionBusy(false);
    }
  }

  const terminal = detail ? isTerminalSessionStatus(detail.status) : true;

  return (
    <div className="track-page">
      <SectionHeading
        eyebrow="Сессия"
        title="Детали сессии"
        description={sessionId}
        action={<div className="track-heading-actions"><Link className="button button--secondary button--small" to="/admin/sessions"><ArrowLeft size={14} /> Все сессии</Link><button type="button" className="button button--secondary button--small" onClick={() => void load()} disabled={loading}><RefreshCw size={14} /> Обновить</button></div>}
      />

      {error && <div className="track-form-error" role="alert">{error}</div>}
      {actionMessage && <div className="track-inline-message is-success" role="status">{actionMessage}{chatLink && <p><a href={chatLink} target="_blank" rel="noopener noreferrer">Открыть ссылку текстового чата</a></p>}</div>}
      {loading ? <div className="track-empty-state"><span className="loading-dot" />Загружаем детали сессии…</div> : !detail ? <section className="track-panel"><div className="track-empty-state"><ShieldCheck size={26} /><strong>Сессия недоступна</strong><span>Проверьте номер обращения и права доступа.</span><Link className="button button--secondary button--small" to="/admin/sessions">Вернуться к списку</Link></div></section> : <>
        <div className="track-call-summary-grid">
          <div className="track-summary-card"><span>Статус</span><strong><StatusBadge tone={sessionStatusTone(detail.status)}>{sessionStatusLabels[detail.status] ?? detail.status}</StatusBadge></strong><small>{detail.status}</small></div>
          <div className="track-summary-card"><span>Создана</span><strong>{formatDate(detail.created_at)}</strong><small>Дата с backend</small></div>
          <div className="track-summary-card"><span>Канал</span><strong>{detail.channel}</strong><small>Session channel</small></div>
          <div className="track-summary-card"><span>Ходы</span><strong>{detail.turns.length}</strong><small>Возвращено API</small></div>
        </div>

        <section className="track-panel">
          <div className="track-panel__heading"><div><span className="track-eyebrow">Действия</span><h2>Управление сессией</h2></div><StatusBadge tone={terminal ? 'warning' : 'neutral'}>{terminal ? 'Терминальное состояние' : 'Доступны действия'}</StatusBadge></div>
          <div className="track-panel__actions">
            <button type="button" className="button button--secondary button--small" onClick={() => void runAction('human')} disabled={terminal || Boolean(busyAction)}><UserRound size={14} /> {busyAction === 'human' ? 'Передаём…' : 'Передать оператору'}</button>
            <button type="button" className="button button--secondary button--small" onClick={() => void runAction('chat')} disabled={terminal || Boolean(busyAction)}><MessageSquare size={14} /> {busyAction === 'chat' ? 'Переводим…' : 'Перевести в чат'}</button>
            <button type="button" className="button button--primary button--small" onClick={() => void runAction('end')} disabled={terminal || Boolean(busyAction)}><Square size={13} /> {busyAction === 'end' ? 'Завершаем…' : 'Завершить сессию'}</button>
          </div>
          <p className="track-panel-footnote"><PhoneForwarded size={12} /> Действия отправляются в сервис. Перевод на сотрудника или в чат зависит от подключённых каналов.</p>
        </section>

        <section className="track-panel">
          <div className="track-panel__heading"><div><span className="track-eyebrow">Транскрипт</span><h2>Транскрипт сессии</h2></div><StatusBadge tone="neutral">{detail.turns.length} ходов</StatusBadge></div>
          {detail.turns.length === 0 ? <div className="track-empty-state"><Clock3 size={24} /><strong>Транскриптов пока нет</strong><span>Backend вернул пустой массив turns.</span></div> : <div className="track-transcript-list">{detail.turns.map((turn, index) => <article className="track-transcript-turn" key={turn.turn_id}>
            <div className="track-transcript-turn__meta"><strong>Ход {turn.sequence_no || index + 1}</strong><span>{formatDate(turn.started_at)}</span><span className="track-code-label">{turn.turn_id}</span></div>
            <p>{turn.redacted_text || 'Текст скрыт или отсутствует.'}</p>
            {turn.intent && <div className="track-intent-chip">Intent: {turn.intent}</div>}
            <div className="track-panel__actions"><button type="button" className="button button--secondary button--small" onClick={() => startCorrection(turn)} disabled={correctionBusy}><Check size={13} /> Исправить текст</button></div>
            {editingTurn?.turn_id === turn.turn_id && <form className="track-edit-form" onSubmit={(event) => void submitCorrection(event)}>
              <div className="track-field"><span>Исправленный текст</span><textarea required value={correctedText} onChange={(event) => setCorrectedText(event.target.value)} rows={4} maxLength={12000} /></div>
              <div className="track-field"><span>Причина исправления</span><select value={correctionReason} onChange={(event) => setCorrectionReason(event.target.value)} required><option value="ASR_error">Ошибка распознавания (ASR_error)</option><option value="Other">Другое</option><option value="Wrong punctuation">Пунктуация</option><option value="Supervisor correction">Исправление супервайзером</option></select></div>
              <div className="track-panel__actions"><button type="button" className="button button--secondary button--small" onClick={() => setEditingTurn(null)} disabled={correctionBusy}>Отмена</button><button type="submit" className="button button--primary button--small" disabled={correctionBusy || !correctedText.trim() || !correctionReason.trim()}>{correctionBusy ? 'Сохраняем…' : 'Сохранить коррекцию'}</button></div>
            </form>}
          </article>)}</div>}
          <p className="track-panel-footnote"><ShieldCheck size={12} /> API предоставляет только redacted_text. Оригинальный текст и аудит отдельно не отображаются в этом контракте; права доступа проверяются backend.</p>
        </section>
      </>}
    </div>
  );
}
