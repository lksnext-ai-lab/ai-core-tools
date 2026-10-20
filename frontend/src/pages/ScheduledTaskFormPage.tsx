import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import {
  apiService,
  type OutputDestination,
  type ScheduledTask,
  type ScheduledTaskVisibility,
} from "../services/api";
import Title from "../components/ui/Title";
import ButtonApp from "../components/ui/ButtonApp";
import {
  FormCheckbox,
  FormField,
  FormRadio,
  FormSelect,
  FormTextArea,
} from "../components/ui/FormField";
import CardApp from "../components/ui/CardApp";

interface AgentOption {
  agent_id: number;
  name: string;
}
type Frequency = "interval" | "daily" | "weekly" | "monthly";

function applyCronToSimpleSchedule(
  cronExpression: string,
  setFrequency: (value: Frequency) => void,
  setInterval: (value: number) => void,
  setTime: (value: string) => void,
  setWeekday: (value: string) => void,
  setMonthDay: (value: string) => void,
) {
  const fields = cronExpression.trim().split(/\s+/);
  if (fields.length !== 5) return;
  const [minute, hour, dayOfMonth, , dayOfWeek] = fields;
  const hourValue = Number(hour);
  const minuteValue = Number(minute);
  if (minute.startsWith("*/") && hour === "*") {
    setFrequency("interval");
    setInterval(Number(minute.slice(2)));
    return;
  }
  if (minute === "0" && hour.startsWith("*/")) {
    setFrequency("interval");
    setInterval(Number(hour.slice(2)) * 60);
    return;
  }
  if (Number.isInteger(hourValue) && Number.isInteger(minuteValue)) {
    setTime(
      `${String(hourValue).padStart(2, "0")}:${String(minuteValue).padStart(2, "0")}`,
    );
  }
  if (dayOfWeek !== "*") {
    setFrequency("weekly");
    setWeekday(dayOfWeek);
    return;
  }
  if (dayOfMonth !== "*") {
    setFrequency("monthly");
    setMonthDay(dayOfMonth);
    return;
  }
  setFrequency("daily");
}

export default function ScheduledTaskFormPage() {
  const { appId, taskId } = useParams();
  const navigate = useNavigate();
  const numericAppId = Number.parseInt(appId ?? "0", 10);
  const editing = taskId !== undefined && taskId !== "new";
  const [agents, setAgents] = useState<AgentOption[]>([]);
  const [task, setTask] = useState<ScheduledTask | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [maxRunsRetained, setMaxRunsRetained] = useState(10);
  const [visibility, setVisibility] =
    useState<ScheduledTaskVisibility>("unpublished");
  const [agentId, setAgentId] = useState("");
  const [input, setInput] = useState("");
  const [timezone, setTimezone] = useState(
    Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
  );
  const [mode, setMode] = useState<"new_per_run" | "continuous">("new_per_run");
  const [frequency, setFrequency] = useState<Frequency>("daily");
  const [interval, setInterval] = useState(60);
  const [time, setTime] = useState("08:00");
  const [weekday, setWeekday] = useState("1");
  const [monthDay, setMonthDay] = useState("1");
  const [saving, setSaving] = useState(false);
  const [loadState, setLoadState] = useState<"loading" | "ready" | "error">(
    "loading",
  );
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [destinations, setDestinations] = useState<OutputDestination[]>([]);
  const [outputDestinationIds, setOutputDestinationIds] = useState<number[]>(
    [],
  );

  useEffect(() => {
    let active = true;
    setTask(null);
    setOutputDestinationIds([]);
    setLoadState("loading");
    void apiService
      .getAgents(numericAppId)
      .then((items) => {
        if (active)
          setAgents(
            items.map((item) => ({ agent_id: item.agent_id, name: item.name })),
          );
      })
      .catch(() => {
        if (active) toast.error("No se pudieron cargar los agentes");
      });
    const destinationsRequest = apiService.getOutputDestinations(numericAppId);
    if (editing) {
      void Promise.all([
        apiService.getScheduledTask(numericAppId, Number(taskId)),
        apiService.getScheduledTaskOutputs(numericAppId, Number(taskId)),
        destinationsRequest,
      ])
        .then(([found, result, loadedDestinations]) => {
          if (!active) return;
          setTask(found);
          setDestinations(loadedDestinations);
          setOutputDestinationIds(
            result.bindings.map((binding) => binding.destination_id),
          );
          setName(found.name);
          setDescription(found.description ?? "");
          setMaxRunsRetained(found.max_runs_retained);
          setVisibility(found.marketplace_visibility);
          setAgentId(String(found.agent_id));
          setInput(
            found.input?.message
              ? String(found.input.message)
              : JSON.stringify(found.input ?? {}, null, 2),
          );
          setTimezone(found.timezone);
          setMode(
            found.conversation_mode === "continuous"
              ? "continuous"
              : "new_per_run",
          );
          applyCronToSimpleSchedule(
            found.cron_expression,
            setFrequency,
            setInterval,
            setTime,
            setWeekday,
            setMonthDay,
          );
          setLoadState("ready");
        })
        .catch(() => {
          if (active) setLoadState("error");
        });
    } else {
      void destinationsRequest
        .then((loadedDestinations) => {
          if (active) {
            setDestinations(loadedDestinations);
            setLoadState("ready");
          }
        })
        .catch(() => {
          if (active) setLoadState("error");
        });
    }
    return () => {
      active = false;
    };
  }, [editing, numericAppId, taskId, loadAttempt]);

  const simpleCron = () => {
    const [hour, minute] = time.split(":").map(Number);
    if (frequency === "interval") {
      return interval >= 60 && interval % 60 === 0
        ? `0 */${interval / 60} * * *`
        : `*/${interval} * * * *`;
    }
    if (frequency === "weekly") return `${minute} ${hour} * * ${weekday}`;
    if (frequency === "monthly") return `${minute} ${hour} ${monthDay} * *`;
    return `${minute} ${hour} * * *`;
  };

  const save = async () => {
    if (loadState !== "ready" || (editing && task?.id !== Number(taskId))) {
      toast.error(
        "Espera a que se carguen la tarea y sus canales antes de guardar",
      );
      return;
    }
    const effectiveCron = simpleCron();
    if (!name.trim() || !agentId || !effectiveCron) {
      toast.error("Completa el nombre, el agente y la programación");
      return;
    }
    let parsedInput: Record<string, unknown> = {};
    if (input.trim()) {
      try {
        parsedInput = JSON.parse(input) as Record<string, unknown>;
      } catch {
        parsedInput = { message: input.trim() };
      }
    }
    setSaving(true);
    try {
      const common = {
        name,
        description: description.trim() || null,
        input: parsedInput,
        cron_expression: effectiveCron,
        timezone,
        max_runs_retained: maxRunsRetained,
        marketplace_visibility: visibility,
      };
      const outputBindings = outputDestinationIds.map((destination_id) => ({
        destination_id,
        enabled: true,
      }));
      const saved = task
        ? await apiService.updateScheduledTask(numericAppId, task.id, common)
        : await apiService.createScheduledTask(numericAppId, {
            ...common,
            agent_id: Number(agentId),
            conversation_mode: mode,
            max_concurrent_runs: 1,
            output_bindings: outputBindings,
          });
      if (task)
        await apiService.setScheduledTaskOutputs(
          numericAppId,
          saved.id,
          outputBindings,
        );
      toast.success(task ? "Tarea actualizada" : "Tarea creada");
      navigate(`/apps/${appId}/scheduled-tasks/${saved.id}`);
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "No se pudo guardar la tarea",
      );
    } finally {
      setSaving(false);
    }
  };

  if (loadState !== "ready" || (editing && task?.id !== Number(taskId))) {
    return;
    <div className="mx-auto max-w-4xl space-y-4">
      <h1 className="text-2xl font-bold text-gray-900">
        {editing ? "Editar tarea programada" : "Nueva tarea programada"}
      </h1>
      {loadState === "error" ? (
        <div
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 p-4"
        >
          <p>
            No se pudieron cargar la tarea y sus canales. Reintenta la carga
            para poder guardar.
          </p>
          <button
            type="button"
            onClick={() => {
              setLoadState("loading");
              setLoadAttempt((attempt) => attempt + 1);
            }}
            className="mt-3 rounded-lg border px-3 py-2"
          >
            Reintentar carga
          </button>
        </div>
      ) : (
        <p role="status">Cargando configuración de la tarea y sus canales…</p>
      )}
      <button
        type="button"
        onClick={() => navigate(`/apps/${appId}/scheduled-tasks`)}
        className="rounded-lg border px-4 py-2"
      >
        Cancelar
      </button>
    </div>;
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <Title variant="titPrincipal" titulo={task ? "Editar tarea programada" : "Nueva tarea programada"} subtitulo="Configura qué agente ejecutar y con qué periodicidad." />
      <div className="space-y-5">
        <FormField
          label="Nombre de la tarea"
          id="task-name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Informe diario"
        />
        <FormTextArea
          label="Descripción (opcional, visible en el marketplace)"
          id="task-description"
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          rows={2}
          maxLength={4000}
          placeholder="Qué produce esta tarea y para quién"
        />
        <FormSelect
          label="Agente"
          id="task-agent"
          value={agentId}
          disabled={Boolean(task)}
          onChange={(event) => setAgentId(event.target.value)}
          options={[
            { value: "", label: "Selecciona un agente" },
            ...agents.map((agent) => ({
              value: agent.agent_id,
              label: agent.name,
            })),
          ]}
        />
        <FormTextArea
          label="Input de la tarea"
          id="task-input"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          rows={5}
          placeholder="Escribe el mensaje inicial o un objeto JSON…"
        />
        <fieldset disabled={Boolean(task)}>
          <legend className="mb-2 text-sm font-medium text-fg dark:text-fg-dark">
            Modo de conversación
          </legend>
          <FormRadio
            label="Cada ejecución empieza una conversación nueva"
            checked={mode === "new_per_run"}
            onChange={() => setMode("new_per_run")}
            className="mb-2 flex gap-2 text-sm"
          />
          <FormRadio
            label="Todas las ejecuciones continúan la misma conversación"
            checked={mode === "continuous"}
            onChange={() => setMode("continuous")}
            className="flex gap-2 text-sm"
          />
          {mode === "continuous" && (
            <p className="mt-1 text-xs text-fg-secondary dark:text-fg-secondary-dark">
              El agente verá lo ocurrido en ejecuciones anteriores, como en una
              conversación normal. Requiere un agente con memoria.
            </p>
          )}
          {task && (
            <p className="mt-1 text-xs text-fg-secondary dark:text-fg-secondary-dark">
              El modo no se puede cambiar una vez creada la tarea.
            </p>
          )}
        </fieldset>
        <CardApp className="p-4">
          <div className="mb-3">
            <h3 className="text-xl font-semibold text-fg dark:text-fg-dark">
              Programación
            </h3>
            <p className="text-sm text-secondary dark:text-secondary-dark mt-1">
              Define la frecuencia sin tener que escribir CRON.
            </p>
          </div>
          <div className="space-y-3">
            <FormSelect
              label="Frecuencia"
              id="task-frequency"
              value={frequency}
              onChange={(event) =>
                setFrequency(event.target.value as Frequency)
              }
              options={[
                { value: "interval", label: "Cada X minutos/horas" },
                { value: "daily", label: "Diariamente" },
                { value: "weekly", label: "Semanalmente" },
                { value: "monthly", label: "Mensualmente" },
              ]}
            />
            {frequency === "interval" && (
              <FormField
                label="Intervalo (minutos)"
                id="task-interval"
                type="number"
                min={1}
                max={1440}
                value={interval}
                onChange={(event) => setInterval(Number(event.target.value))}
              />
            )}
            {frequency !== "interval" && (
              <FormField
                label="Hora"
                id="task-time"
                type="time"
                value={time}
                onChange={(event) => setTime(event.target.value)}
                inputClassName="dark:[color-scheme:dark] [&::-webkit-datetime-edit-hour-field:focus]:bg-[var(--color-bronze-bg-sof)] [&::-webkit-datetime-edit-hour-field:focus]:text-[var(--text-bronze)] [&::-webkit-datetime-edit-minute-field:focus]:bg-[var(--color-bronze-bg-sof)] [&::-webkit-datetime-edit-minute-field:focus]:text-[var(--text-bronze)] dark:[&::-webkit-datetime-edit-hour-field:focus]:bg-bronze-bg-dark dark:[&::-webkit-datetime-edit-hour-field:focus]:text-bronze-dark dark:[&::-webkit-datetime-edit-minute-field:focus]:bg-bronze-bg-dark dark:[&::-webkit-datetime-edit-minute-field:focus]:text-bronze-dark [&::-webkit-calendar-picker-indicator]:cursor-pointer"
              />
            )}
            {frequency === "weekly" && (
              <FormSelect
                label="Día de la semana"
                id="task-weekday"
                value={weekday}
                onChange={(event) => setWeekday(event.target.value)}
                options={[
                  { value: "1", label: "Lunes" },
                  { value: "2", label: "Martes" },
                  { value: "3", label: "Miércoles" },
                  { value: "4", label: "Jueves" },
                  { value: "5", label: "Viernes" },
                  { value: "6", label: "Sábado" },
                  { value: "0", label: "Domingo" },
                ]}
              />
            )}
            {frequency === "monthly" && (
              <FormField
                label="Día del mes"
                id="task-month-day"
                type="number"
                min={1}
                max={28}
                value={monthDay}
                onChange={(event) => setMonthDay(event.target.value)}
              />
            )}
            <p className="text-sm text-secondary dark:text-secondary-dark">
              Se guardará como{" "}
              <code className="rounded bg-white px-1 font-mono">
                {simpleCron()}
              </code>.
            </p>
          </div>
        </CardApp>
        <CardApp className="p-4">
          <div className="mb-3">
            <h3 className="text-xl font-semibold text-fg dark:text-fg-dark">
              Canales de salida
            </h3>
            <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">
              Selecciona los canales registrados en App Settings para esta
              tarea.
            </p>
          </div>
          {destinations.length === 0 ? (
            <div className="space-y-2">
              <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">
                Todavía no hay canales registrados para esta aplicación.
              </p>
              <Link
                to={`/apps/${appId}/settings/output-destinations`}
                className="inline-block text-xs font-medium text-bronze dark:text-bronze-dark transition-colors"
              >
                Ir a App Settings para registrar canales
              </Link>
            </div>
          ) : (
            <>
              <div className="space-y-2">
                {destinations.map((destination) => (
                  <div
                    key={destination.id}
                    className="flex items-center gap-2 rounded-lg border p-3 text-sm"
                  >
                    <FormCheckbox
                      id={`output-destination-${destination.id}`}
                      label={destination.name}
                      checked={outputDestinationIds.includes(destination.id)}
                      onChange={(event) =>
                        setOutputDestinationIds((items) =>
                          event.target.checked
                            ? [...items, destination.id]
                            : items.filter((id) => id !== destination.id),
                        )
                      }
                      className="min-w-0 flex-1"
                    />
                    <span className="text-xs text-fg-secondary dark:text-fg-secondary-dark">
                      {destination.provider_key === "webhook"
                        ? "Webhook"
                        : "Teams"}
                    </span>
                  </div>
                ))}
              </div>
              <Link
                to={`/apps/${appId}/settings/output-destinations`}
                className="mt-3 inline-block text-xs  text-bronze dark:text-bronze-dark transition-colors"
              >
                Administrar canales en App Settings
              </Link>
            </>
          )}
        </CardApp>
        <FormField
          label="Zona horaria"
          id="task-timezone"
          value={timezone}
          onChange={(event) => setTimezone(event.target.value)}
        />
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField
            label="Ejecuciones a conservar"
            id="task-retention"
            type="number"
            min={1}
            max={100}
            value={maxRunsRetained}
            onChange={(event) =>
              setMaxRunsRetained(
                Math.min(100, Math.max(1, Number(event.target.value) || 1)),
              )
            }
            helpText="Al superar el límite se borran las más antiguas, con sus archivos. Las que tengan notificaciones vigentes se conservan hasta que caduquen."
          />
          <div>
            <FormSelect
              label="Visibilidad en el marketplace"
              id="task-visibility"
              value={visibility}
              onChange={(event) =>
                setVisibility(event.target.value as ScheduledTaskVisibility)
              }
              options={[
                { value: "unpublished", label: "No publicada" },
                { value: "private", label: "Privada · miembros de la app" },
                { value: "public", label: "Pública · todos los usuarios" },
              ]}
            />
            <p className="mt-1 text-xs text-fg-secondary dark:text-fg-secondary-dark">
              En el marketplace solo se muestran los resultados, nunca el input.
            </p>
          </div>
        </div>
        <div className="flex justify-end gap-3">
          <ButtonApp
            label="Cancelar"
            type="button"
            variant="secondary"
            size="medium"
            onClick={() =>
              navigate(
                task
                  ? `/apps/${appId}/scheduled-tasks/${task.id}`
                  : `/apps/${appId}/scheduled-tasks`,
              )
            }
          />
          <ButtonApp
            label={saving ? "Guardando…" : "Guardar y activar"}
            type="button"
            variant="primary"
            size="medium"
            disabled={saving}
            loading={saving}
            onClick={() => {
              void save();
            }}
          />
        </div>
      </div>
    </div>
  );
}
