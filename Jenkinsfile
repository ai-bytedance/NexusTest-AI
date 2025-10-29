pipeline {
    agent any

    environment {
        VENV_DIR = '.venv'
    }

    stages {
        stage('Setup') {
            steps {
                sh '''
                    python3 -m venv ${VENV_DIR}
                    . ${VENV_DIR}/bin/activate
                    pip install --upgrade pip httpx
                '''
            }
        }

        stage('Trigger') {
            steps {
                withCredentials([
                    usernamePassword(credentialsId: 'nt-api-user', usernameVariable: 'NT_EMAIL', passwordVariable: 'NT_PASSWORD'),
                    string(credentialsId: 'nt-api-base', variable: 'NT_API_BASE'),
                    string(credentialsId: 'nt-project-id', variable: 'NT_PROJECT_ID'),
                    string(credentialsId: 'nt-suite-id', variable: 'NT_SUITE_ID'),
                    string(credentialsId: 'nt-threshold', variable: 'NT_PASS_THRESHOLD'),
                ]) {
                    sh '''
                        . ${VENV_DIR}/bin/activate
                        python scripts/nt_cli.py --no-wait --format json --output-file nt_trigger.json
                    '''
                }
            }
        }

        stage('Wait') {
            steps {
                withCredentials([
                    usernamePassword(credentialsId: 'nt-api-user', usernameVariable: 'NT_EMAIL', passwordVariable: 'NT_PASSWORD'),
                    string(credentialsId: 'nt-api-base', variable: 'NT_API_BASE'),
                    string(credentialsId: 'nt-project-id', variable: 'NT_PROJECT_ID'),
                    string(credentialsId: 'nt-suite-id', variable: 'NT_SUITE_ID'),
                    string(credentialsId: 'nt-threshold', variable: 'NT_PASS_THRESHOLD'),
                ]) {
                    sh '''
                        . ${VENV_DIR}/bin/activate
                        export NT_TASK_ID=$(python - <<'PY'
import json
with open('nt_trigger.json', 'r', encoding='utf-8') as handle:
    data = json.load(handle)
print(data.get('task_id', ''))
PY
)
                        export NT_REPORT_ID=$(python - <<'PY'
import json
with open('nt_trigger.json', 'r', encoding='utf-8') as handle:
    data = json.load(handle)
print(data.get('report_id', ''))
PY
)
                        python scripts/nt_cli.py --format json --output-file nt_result.json
                    '''
                }
            }
        }

        stage('Publish') {
            steps {
                sh '''
                    . ${VENV_DIR}/bin/activate
                    python - <<'PY'
import json
import os

path = 'nt_result.json'
if os.path.exists(path):
    with open(path, 'r', encoding='utf-8') as handle:
        data = json.load(handle)
else:
    data = {
        'status': 'error',
        'outcome': 'error',
        'message': 'nt_cli.py did not create nt_result.json',
        'exit_code': 1,
    }

print('NetTests summary:')
print(json.dumps(data, indent=2))
if data.get('exit_code') not in (0, None):
    raise SystemExit(data['exit_code'])
PY
                '''
            }
        }
    }

    post {
        always {
            archiveArtifacts artifacts: 'nt_*.json', allowEmptyArchive: true
        }
    }
}
