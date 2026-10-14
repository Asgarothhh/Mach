import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, ArrowRight, Building2, Check, CheckCircle2, Clock3, PhoneCall, ShieldCheck, Sparkles } from 'lucide-react';
import { SectionHeading } from '../../../shared/components/SectionHeading';
import { StatusBadge } from '../../../shared/components/StatusBadge';
import { env } from '../../../shared/config/env';
import { useTenant } from '../../tenant/model/TenantContext';
import type { InboundAdapter, RoutePolicy, TenantCreateInput, TenantProfile } from '../../../shared/types/track1';
import { createTenant, listTenants, startTenantTestCall, updateTenantProfile, validateTenantOnboarding } from '../services/onboarding.service';

const stepLabels = ['Компания', 'Сценарий', 'Каналы', 'Проверка'];
const initialForm: TenantCreateInput = {
  display_name: '',
  greeting: 'Здравствуйте! Вы позвонили в компанию. Я голосовой помощник. Чем могу помочь?',
  route_policy: 'chat_for_complex',
  complexity_threshold_seconds: 40,
  chat_provider: 'mock',
  chat_destination_label: 'Демо-чат компании',
  inbound_adapter: 'mock',
  inbound_endpoint_label: 'Mock incoming call',
  human_transfer_label: 'Тестовая очередь сотрудников',
  human_transfer_enabled: true,
  consent_notice: 'Разговор может обрабатываться для подготовки ответа. Если вы не согласны, попросите соединить вас с сотрудником.',
  consent_notice_version: 'notice-r1',
};

export function OnboardingPage() {
  const navigate = useNavigate();
  const { setActiveTenant, registerTenant } = useTenant();
  const [step, setStep] = useState(0);
  const [form, setForm] = useState<TenantCreateInput>(initialForm);
  const [profileMode, setProfileMode] = useState<'create' | 'existing'>('create');
  const [profiles, setProfiles] = useState<TenantProfile[]>([]);
  const [selectedProfileId, setSelectedProfileId] = useState('');
  const [profilesLoading, setProfilesLoading] = useState(true);
  const [startedAt] = useState(() => Date.now());
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const timer = window.setInterval(() => setNow(Date.now()), 1000); return () => window.clearInterval(timer); }, []);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [blockers, setBlockers] = useState<string[]>([]);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [createdTenant, setCreatedTenant] = useState<TenantProfile | null>(null);
  const [testCallId, setTestCallId] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    void listTenants().then((items) => { if (active) { setProfiles(items); setSelectedProfileId(items[0]?.tenant_id ?? ''); } }).catch(() => { if (active) setProfiles([]); }).finally(() => { if (active) setProfilesLoading(false); });
    return () => { active = false; };
  }, []);
  const elapsedSeconds = Math.max(1, Math.round((now - startedAt) / 1000));
  const elapsedLabel = useMemo(() => elapsedSeconds < 60 ? `${elapsedSeconds} сек.` : `${Math.floor(elapsedSeconds / 60)} мин. ${elapsedSeconds % 60} сек.`, [elapsedSeconds]);

  function update<K extends keyof TenantCreateInput>(key: K, value: TenantCreateInput[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function chooseExistingProfile(profileId: string) {
    setSelectedProfileId(profileId);
    const profile = profiles.find((item) => item.tenant_id === profileId);
    if (!profile) return;
    setForm({ display_name: profile.display_name, greeting: profile.greeting, route_policy: profile.route_policy, complexity_threshold_seconds: profile.complexity_threshold_seconds, chat_provider: profile.chat_provider, chat_destination_label: profile.chat_destination_label, inbound_adapter: profile.inbound_adapter, inbound_endpoint_label: profile.inbound_endpoint_label, human_transfer_label: profile.human_transfer_label, human_transfer_enabled: profile.human_transfer_enabled, consent_notice: profile.consent_notice, consent_notice_version: profile.consent_notice_version });
    setCreatedTenant(profile);
  }

  function validateStep(): boolean {
    setError(null);
    if (step === 0 && !form.display_name.trim()) {
      setError('Укажите название компании, чтобы продолжить.');
      return false;
    }
    if (step === 1 && form.greeting.trim().length < 12) {
      setError('Добавьте приветствие длиной не менее 12 символов.');
      return false;
    }
    if (step === 2 && form.inbound_adapter === 'sip' && !form.inbound_endpoint_label.trim()) {
      setError('Укажите ссылку на настроенный SIP endpoint.');
      return false;
    }
    if (step === 2 && env.demoMode && form.inbound_adapter === 'sip') {
      setError('В демо можно создать только синтетический Mock call. SIP-тест доступен после подключения backend и credentials.');
      return false;
    }
    return true;
  }

  async function finishSetup() {
    if (!validateStep()) return;
    setBusy(true);
    setError(null);
    setBlockers([]);
    try {
      const selectedProfile = profiles.find((item) => item.tenant_id === selectedProfileId);
      const targetProfile = profileMode === 'existing' ? selectedProfile : (createdTenant && createdTenant.display_name === form.display_name ? createdTenant : undefined);
      if (profileMode === 'existing' && !targetProfile) throw new Error('Выберите существующий профиль компании.');
      const tenant = targetProfile ? await updateTenantProfile(targetProfile.tenant_id, form) : await createTenant(form);
      setCreatedTenant(tenant);
      registerTenant(tenant);
      setActiveTenant(tenant.tenant_id, tenant.display_name);
      const validation = await validateTenantOnboarding(tenant.tenant_id, form.display_name, form.greeting, now - startedAt);
      setBlockers(validation.blockers);
      setWarnings(validation.warnings);
      if (!validation.ready) {
        setError('Есть обязательные поля, которые нужно исправить. Проверьте список ниже.');
        return;
      }
      const testCall = await startTenantTestCall(tenant.tenant_id, form.inbound_adapter, tenant.display_name);
      if (testCall.status === 'failed') {
        setError(testCall.message || 'Тестовый вызов не прошёл. Проверьте настройки канала.');
        return;
      }
      setTestCallId(testCall.call_id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось завершить настройку. Проверьте API и права доступа.');
    } finally {
      setBusy(false);
    }
  }

  const title = ['Профиль компании', 'Как агент должен отвечать?', 'Входящий канал и передача', 'Уведомление и тест'][step];

  return (
    <div className="track-page track-page--narrow">
      <SectionHeading
        eyebrow="Подключение"
        title="Подключим голосового агента"
        description="Создайте базовый профиль компании и проверьте входящий тестовый звонок. Цель — пройти мастер за пять минут."
        action={<StatusBadge tone={env.demoMode ? 'demo' : 'neutral'} dot>{env.demoMode ? 'Демо-режим' : 'Кабинет компании'}</StatusBadge>}
      />

      <div className="track-onboarding-summary">
        <div className="track-onboarding-summary__icon"><Clock3 size={19} /></div>
        <div><strong>Время настройки: {elapsedLabel}</strong><p>Измерение в интерфейсе — ориентир. Сервис должен уложиться примерно в пять минут.</p></div>
        <span className={`track-time-target ${elapsedSeconds <= 300 ? 'is-ok' : 'is-warning'}`}>{elapsedSeconds <= 300 ? 'Цель ≤ 5 мин' : 'Больше 5 мин'}</span>
      </div>

      <div className="track-wizard-card">
        <div className="track-wizard-progress" aria-label={`Шаг ${step + 1} из ${stepLabels.length}`}>
          {stepLabels.map((label, index) => (
            <div className={`track-wizard-progress__step ${index === step ? 'is-current' : ''} ${index < step || testCallId ? 'is-done' : ''}`} key={label}>
              <span>{index < step || testCallId ? <Check size={15} /> : index + 1}</span><small>{label}</small>
            </div>
          ))}
        </div>

        {!testCallId ? <>
          <div className="track-wizard-heading"><span className="track-step-kicker">ШАГ {step + 1} / 4</span><h2>{title}</h2><p>{['Укажите, для какой компании будет отвечать помощник.', 'Задайте приветствие и правила выбора канала ответа.', 'Выберите входящий канал и резервные способы связи.', 'Проверьте уведомление о разговоре и запустите тестовый входящий вызов.'][step]}</p></div>

          {step === 0 && <div className="track-form-stack">
            <fieldset className="track-fieldset"><legend>Профиль компании</legend>
              <label className={`track-choice ${profileMode === 'create' ? 'is-selected' : ''}`}><input type="radio" name="tenant-mode" checked={profileMode === 'create'} onChange={() => { setProfileMode('create'); setCreatedTenant(null); setForm(initialForm); }} /><span><strong>Создать новый профиль</strong><small>Настроить отдельный профиль компании.</small></span></label>
              <label className={`track-choice ${profileMode === 'existing' ? 'is-selected' : ''}`}><input type="radio" name="tenant-mode" checked={profileMode === 'existing'} onChange={() => { setProfileMode('existing'); const profile = profiles.find((item) => item.tenant_id === selectedProfileId); if (profile) chooseExistingProfile(profile.tenant_id); }} /><span><strong>Выбрать существующий</strong><small>Использовать профиль, доступный вашей учётной записи.</small></span></label>
            </fieldset>
            {profileMode === 'existing' && <label className="track-field"><span>Доступные профили</span><select value={selectedProfileId} onChange={(event) => chooseExistingProfile(event.target.value)} disabled={profilesLoading || profiles.length === 0}><option value="">{profilesLoading ? 'Загружаем профили…' : 'Нет доступных профилей'}</option>{profiles.map((profile) => <option value={profile.tenant_id} key={profile.tenant_id}>{profile.display_name}</option>)}</select><small>Production-список должен приходить от backend только с tenant, на которые у пользователя есть права.</small></label>}
            {profileMode === 'create' && <label className="track-field"><span>Название компании <b>*</b></span><input autoFocus value={form.display_name} onChange={(event) => update('display_name', event.target.value)} placeholder="Например, ООО «Моя компания»" maxLength={120} /><small>Это имя будет использоваться в профиле и приветствии. Не указывайте реальные данные звонящих.</small></label>}
            <div className="track-info-panel"><Building2 size={20} /><div><strong>Изолированный профиль компании</strong><p>Источники, звонки, сценарии и настройки хранятся в рамках одной компании. Публичные материалы МТС не подключаются автоматически.</p></div></div>
          </div>}

          {step === 1 && <div className="track-form-stack">
            <label className="track-field"><span>Приветствие</span><textarea value={form.greeting} onChange={(event) => update('greeting', event.target.value)} rows={4} maxLength={600} /><small>{form.greeting.length}/600 символов. Не обещайте действий, которые не подтверждены интеграциями.</small></label>
            <fieldset className="track-fieldset"><legend>Правило маршрутизации</legend>
              <label className={`track-choice ${form.route_policy === 'voice_first' ? 'is-selected' : ''}`}><input type="radio" name="route-policy" checked={form.route_policy === 'voice_first'} onChange={() => update('route_policy', 'voice_first' as RoutePolicy)} /><span><strong>Отвечать голосом</strong><small>Стандартный режим для коротких вопросов по одобренным источникам.</small></span></label>
              <label className={`track-choice ${form.route_policy === 'chat_for_complex' ? 'is-selected' : ''}`}><input type="radio" name="route-policy" checked={form.route_policy === 'chat_for_complex'} onChange={() => update('route_policy', 'chat_for_complex' as RoutePolicy)} /><span><strong>Предлагать чат для сложных вопросов</strong><small>Сначала предложить переход, получить согласие и лишь потом передать контекст.</small></span></label>
              <label className={`track-choice ${form.route_policy === 'human_for_complex' ? 'is-selected' : ''}`}><input type="radio" name="route-policy" checked={form.route_policy === 'human_for_complex'} onChange={() => update('route_policy', 'human_for_complex' as RoutePolicy)} /><span><strong>Переводить сложные обращения человеку</strong><small>В тестовом окружении результат зависит от настроенного transfer adapter.</small></span></label>
            </fieldset>
            {form.route_policy !== 'voice_first' && <label className="track-field"><span>Порог предложения передачи · секунды</span><input type="number" min={15} max={180} value={form.complexity_threshold_seconds} onChange={(event) => update('complexity_threshold_seconds', Number(event.target.value))} /></label>}
          </div>}

          {step === 2 && <div className="track-form-stack">
            <fieldset className="track-fieldset"><legend>Входящий канал</legend>
              <label className={`track-choice ${form.inbound_adapter === 'mock' ? 'is-selected' : ''}`}><input type="radio" name="inbound-adapter" checked={form.inbound_adapter === 'mock'} onChange={() => update('inbound_adapter', 'mock' as InboundAdapter)} /><span><strong>Тестовый вызов</strong><small>Проверка сценария в кабинете, без телефонной сети.</small></span><StatusBadge tone="demo">Доступно</StatusBadge></label>
              <label className={`track-choice ${form.inbound_adapter === 'sip' ? 'is-selected' : ''}`}><input type="radio" name="inbound-adapter" checked={form.inbound_adapter === 'sip'} onChange={() => update('inbound_adapter', 'sip' as InboundAdapter)} /><span><strong>Телефонный канал</strong><small>Доступен только после отдельного подключения входящей линии.</small></span></label>
            </fieldset>
            <label className="track-field"><span>Название входящего канала</span><input value={form.inbound_endpoint_label} onChange={(event) => update('inbound_endpoint_label', event.target.value)} placeholder={form.inbound_adapter === 'mock' ? 'Тестовый входящий вызов' : 'Входящая линия'} /></label>
            <div className="track-field-row">
              <label className="track-field"><span>Канал чата</span><select value={form.chat_provider} onChange={(event) => update('chat_provider', event.target.value as 'none' | 'mock')}><option value="mock">Текстовый чат</option><option value="none">Пока не настроен</option></select></label>
              <label className="track-field"><span>Название чата</span><input value={form.chat_destination_label} onChange={(event) => update('chat_destination_label', event.target.value)} disabled={form.chat_provider === 'none'} /></label>
            </div>
            <label className="track-field"><span>Куда передавать сотруднику</span><input value={form.human_transfer_label} onChange={(event) => update('human_transfer_label', event.target.value)} disabled={!form.human_transfer_enabled} /></label>
            <label className="track-check"><input type="checkbox" checked={form.human_transfer_enabled} onChange={(event) => update('human_transfer_enabled', event.target.checked)} /><span><strong>Предусмотреть передачу человеку</strong><small>Наличие интерфейса не означает, что реальная очередь уже подключена.</small></span></label>
          </div>}

          {step === 3 && <div className="track-form-stack">
            <label className="track-field"><span>Уведомление о разговоре <b>*</b></span><textarea value={form.consent_notice} onChange={(event) => update('consent_notice', event.target.value)} rows={4} maxLength={900} /><small>Текст уведомления и действие при отказе согласует владелец компании.</small></label>
            <label className="track-field"><span>Версия уведомления</span><input value={form.consent_notice_version} onChange={(event) => update('consent_notice_version', event.target.value)} maxLength={64} /></label>
            <div className="track-info-panel track-info-panel--privacy"><ShieldCheck size={20} /><div><strong>Конфиденциальность по умолчанию</strong><p>Сырой звук не сохраняется по умолчанию. Не сообщайте паспортные данные и номера карт. Этот мастер проверяет сценарий, а не телефонную сеть.</p></div></div>
          </div>}

          {error && <div className="track-form-error" role="alert">{error}</div>}
          {blockers.length > 0 && <div className="track-form-error" role="alert"><strong>Исправьте перед продолжением</strong><ul>{blockers.map((item) => <li key={item}>{item}</li>)}</ul></div>}
          {warnings.length > 0 && <div className="track-notice-list">{warnings.map((item) => <p key={item}>{item}</p>)}</div>}

          <div className="track-wizard-actions">
            <button type="button" className="button button--secondary" onClick={() => { setError(null); setStep((current) => Math.max(0, current - 1)); }} disabled={step === 0 || busy}><ArrowLeft size={16} /> Назад</button>
            {step < 3 ? <button type="button" className="button button--primary" onClick={() => validateStep() && setStep((current) => Math.min(3, current + 1))}>Продолжить <ArrowRight size={16} /></button> : <button type="button" className="button button--primary" onClick={finishSetup} disabled={busy}>{busy ? <><span className="loading-dot" /> Проверяю и запускаю…</> : <><PhoneCall size={16} /> Создать профиль и тестовый звонок</>}</button>}
          </div>
        </> : <div className="track-onboarding-success">
          <div className="track-success-icon"><CheckCircle2 size={32} /></div>
          <span className="track-step-kicker">Готово</span>
          <h2>Профиль настроен</h2>
          <p>Для «{form.display_name}» создан тестовый вызов. Это проверка сценария, а не подключение телефонной сети.</p>
          <div className="track-result-list">
            <div><CheckCircle2 size={17} /><span>Профиль компании</span><strong>Создан</strong></div>
            <div><CheckCircle2 size={17} /><span>Уведомление о разговоре</span><strong>{form.consent_notice_version}</strong></div>
            <div><CheckCircle2 size={17} /><span>Тестовый вызов</span><strong>{testCallId}</strong></div>
            <div><Clock3 size={17} /><span>Время настройки на клиенте</span><strong>{elapsedLabel}</strong></div>
          </div>
          <div className="track-info-panel"><Sparkles size={19} /><div><strong>Следующий шаг</strong><p>Проверьте историю звонков, маршрут и транскрипт. Далее подключаются реальные адаптеры и одобренные источники конкретного tenant.</p></div></div>
          <div className="track-wizard-actions track-wizard-actions--center"><button className="button button--secondary" onClick={() => navigate(`/calls/${testCallId}`)}>Открыть тестовый звонок</button><button className="button button--primary" onClick={() => navigate('/calls')}>Перейти к истории звонков <ArrowRight size={16} /></button></div>
        </div>}
      </div>
      <p className="track-page-footnote">{env.demoMode ? 'Демо: создаются синтетические записи профиля и звонка. Тест не обращается к телефонной сети и не связывается с реальным клиентом.' : 'Доступ и настройки проверяет сервис. Если телефонный канал ещё не подключён, это будет видно отдельно.'}</p>
    </div>
  );
}
