import requests
import time
from datetime import datetime
from typing import Dict, List, Optional


class GitHubActionsMonitor:
    def __init__(self, repo_owner: str, repo_name: str, github_token: str):
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.headers = {
            "Authorization": f"Bearer {github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"
        }
        self.base_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}"
        self.monitored_runs = {}

    def get_workflow_runs(self, branch: str = None, status: str = None) -> List[Dict]:
        """Obtiene las ejecuciones de workflows"""
        url = f"{self.base_url}/actions/runs"
        params = {"per_page": 10}  # Limitar para mejor rendimiento

        if branch:
            params['branch'] = branch
        if status:
            params['status'] = status

        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json().get('workflow_runs', [])
        except requests.exceptions.RequestException as e:
            print(f"Error al obtener workflow runs: {e}")
            return []

    def get_run_details(self, run_id: int) -> Optional[Dict]:
        """Obtiene detalles de una ejecución específica"""
        url = f"{self.base_url}/actions/runs/{run_id}"
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error al obtener detalles del run {run_id}: {e}")
            return None

    def format_duration(self, start_time: str, end_time: str = None) -> str:
        """Calcula duración de la ejecución"""
        try:
            start = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            end = datetime.fromisoformat(end_time.replace(
                'Z', '+00:00')) if end_time else datetime.now().astimezone()

            duration = end - start
            total_seconds = int(duration.total_seconds())
            minutes = total_seconds // 60
            seconds = total_seconds % 60

            return f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"
        except:
            return "Desconocida"

    def create_start_message(self, run_data: Dict) -> str:
        """Mensaje para inicio de workflow"""
        workflow_name = run_data.get('name', 'Workflow')
        branch = run_data.get('head_branch', 'rama desconocida')
        actor = run_data.get('actor', {}).get('login', 'Usuario')
        run_number = run_data.get('run_number', 'N/A')
        commit_msg = run_data.get('head_commit', {}).get('message', '')

        # Truncar mensaje de commit
        if len(commit_msg) > 80:
            commit_msg = commit_msg[:80] + "..."

        return f"""🚀 **GitHub Action Iniciado**

**Repo:** {self.repo_owner}/{self.repo_name}
**Workflow:** {workflow_name} (#{run_number})
**Rama:** {branch}
**Por:** {actor}
**Commit:** {commit_msg}

[Ver en GitHub]({run_data.get('html_url', '#')})"""

    def create_completion_message(self, run_data: Dict) -> str:
        """Mensaje para finalización de workflow"""
        workflow_name = run_data.get('name', 'Workflow')
        branch = run_data.get('head_branch', 'rama desconocida')
        conclusion = run_data.get('conclusion', 'unknown')
        run_number = run_data.get('run_number', 'N/A')

        # Emoji y estado según resultado
        status_map = {
            'success': ('✅', 'EXITOSO'),
            'failure': ('❌', 'FALLIDO'),
            'cancelled': ('⏹️', 'CANCELADO'),
            'skipped': ('⏭️', 'OMITIDO')
        }
        emoji, status_text = status_map.get(conclusion, ('⚠️', 'COMPLETADO'))

        duration = self.format_duration(
            run_data.get('created_at'),
            run_data.get('updated_at')
        )

        return f"""{emoji} **GitHub Action {status_text}**

**Repo:** {self.repo_owner}/{self.repo_name}
**Workflow:** {workflow_name} (#{run_number})
**Rama:** {branch}
**Duración:** {duration}

[Ver en GitHub]({run_data.get('html_url', '#')})"""

    def monitor(self, branch: str = None, poll_interval: int = 30, send_notification=None):
        """Monitorea workflows y envía notificaciones"""
        print(
            f"🔍 Monitoreando GitHub Actions: {self.repo_owner}/{self.repo_name}")
        if branch:
            print(f"📍 Rama: {branch}")
        print(f"⏱️  Intervalo: {poll_interval}s\n")

        while True:
            try:
                # Obtener workflows activos
                active_runs = (
                    self.get_workflow_runs(branch=branch, status='queued') +
                    self.get_workflow_runs(branch=branch, status='in_progress')
                )

                # Procesar workflows nuevos
                for run in active_runs:
                    run_id = run['id']

                    if run_id not in self.monitored_runs:
                        # Nuevo workflow detectado
                        self.monitored_runs[run_id] = {
                            'notified_start': False,
                            'notified_end': False
                        }

                        # Enviar notificación de inicio
                        if send_notification:
                            message = self.create_start_message(run)
                            send_notification(message)
                            self.monitored_runs[run_id]['notified_start'] = True
                            print(
                                f"📤 Notificación de inicio enviada: Run #{run.get('run_number')}")

                # Verificar workflows completados
                for run_id in list(self.monitored_runs.keys()):
                    if self.monitored_runs[run_id]['notified_end']:
                        continue

                    run_details = self.get_run_details(run_id)
                    if run_details and run_details['status'] == 'completed':
                        # Enviar notificación de finalización
                        if send_notification:
                            message = self.create_completion_message(
                                run_details)
                            send_notification(message)
                            self.monitored_runs[run_id]['notified_end'] = True
                            print(
                                f"📤 Notificación de fin enviada: Run #{run_details.get('run_number')}")

                # Limpiar workflows antiguos (mantener solo últimos 50)
                if len(self.monitored_runs) > 50:
                    old_runs = list(self.monitored_runs.keys())[:-30]
                    for old_run in old_runs:
                        del self.monitored_runs[old_run]

                time.sleep(poll_interval)

            except KeyboardInterrupt:
                print("\n⏹️  Monitoreo detenido por el usuario")
                break
            except Exception as e:
                print(f"❌ Error: {e}")
                time.sleep(poll_interval)


def notify_workflow_status(message: str):
    """
    🔧 TODO: Implementar funcion de notificacion
    """
    print("📨 MENSAJE PARA MATTERMOST:")
    print("-" * 60)
    print(message)
    print("-" * 60)
    print()

    # 👇 Aquí va tu función real de Mattermost
    # tu_funcion_mattermost(message)


def main():
    # ⚙️ CONFIGURACIÓN
    REPO_OWNER = "hdelafuente"
    REPO_NAME = "github-workflow-monitor"
    GITHUB_TOKEN = ""
    BRANCH = "main"
    POLL_INTERVAL = 30

    # Validar configuración
    if not all([REPO_OWNER, REPO_NAME, GITHUB_TOKEN]):
        print("❌ Error: Configura REPO_OWNER, REPO_NAME y GITHUB_TOKEN")
        return

    # Crear monitor y iniciar
    monitor = GitHubActionsMonitor(REPO_OWNER, REPO_NAME, GITHUB_TOKEN)
    monitor.monitor(
        branch=BRANCH,
        poll_interval=POLL_INTERVAL,
        send_notification=notify_workflow_status
    )


if __name__ == "__main__":
    main()
