use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum PresenceState {
    Idle,
    Listening,
    Transcribing,
    Routing,
    Planning,
    WaitingForApproval,
    Executing,
    Verifying,
    Recovering,
    Speaking,
    Degraded,
    Failed,
}

impl PresenceState {
    fn label(&self) -> &'static str {
        match self {
            Self::Idle => "Idle",
            Self::Listening => "Listening",
            Self::Transcribing => "Transcribing",
            Self::Routing => "Routing",
            Self::Planning => "Planning",
            Self::WaitingForApproval => "Waiting for approval",
            Self::Executing => "Executing",
            Self::Verifying => "Verifying",
            Self::Recovering => "Recovering",
            Self::Speaking => "Speaking",
            Self::Degraded => "Degraded",
            Self::Failed => "Failed",
        }
    }
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct PresencePayload {
    pub status: PresenceState,
    pub current_task: bool,
    pub pending_approval: bool,
    pub microphone_enabled: bool,
    pub planner_status: String,
    pub stt_status: String,
    pub tts_status: String,
    pub accessibility_status: String,
    pub privacy_mode: String,
}

impl Default for PresencePayload {
    fn default() -> Self {
        Self {
            status: PresenceState::Idle,
            current_task: false,
            pending_approval: false,
            microphone_enabled: true,
            planner_status: "unloaded".into(),
            stt_status: "unloaded".into(),
            tts_status: "unloaded".into(),
            accessibility_status: "not_determined".into(),
            privacy_mode: "ephemeral".into(),
        }
    }
}

#[derive(Debug, PartialEq, Eq)]
pub struct PresenceLabels {
    pub status: String,
    pub task: String,
    pub approval: String,
    pub microphone: String,
    pub planner: String,
    pub stt: String,
    pub tts: String,
    pub accessibility: String,
    pub privacy: String,
}

impl PresencePayload {
    pub fn labels(&self) -> PresenceLabels {
        PresenceLabels {
            status: format!("Status: {}", self.status.label()),
            task: format!(
                "Current task: {}",
                if self.current_task { "active" } else { "none" }
            ),
            approval: format!(
                "Pending approval: {}",
                if self.pending_approval { "yes" } else { "none" }
            ),
            microphone: format!(
                "Microphone: {}",
                if self.microphone_enabled {
                    "enabled"
                } else {
                    "disabled"
                }
            ),
            planner: format!("Local planner: {}", bounded_status(&self.planner_status)),
            stt: format!("STT: {}", bounded_status(&self.stt_status)),
            tts: format!("TTS: {}", bounded_status(&self.tts_status)),
            accessibility: format!(
                "Accessibility: {}",
                bounded_status(&self.accessibility_status)
            ),
            privacy: format!("Privacy: {}", bounded_status(&self.privacy_mode)),
        }
    }
}

fn bounded_status(value: &str) -> &str {
    const ALLOWED: &[&str] = &[
        "unavailable",
        "unloaded",
        "loading",
        "ready",
        "busy",
        "idle_cached",
        "evicting",
        "degraded",
        "failed",
        "not_determined",
        "denied",
        "granted",
        "revoked",
        "ephemeral",
        "retain_transcripts",
    ];
    if ALLOWED.contains(&value) {
        value
    } else {
        "unavailable"
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn presence_payload_labels_are_bounded_and_contain_no_transcript() {
        let payload = PresencePayload {
            status: PresenceState::WaitingForApproval,
            current_task: true,
            pending_approval: true,
            microphone_enabled: true,
            planner_status: "ready".into(),
            stt_status: "degraded".into(),
            tts_status: "ready".into(),
            accessibility_status: "not_determined".into(),
            privacy_mode: "ephemeral".into(),
        };
        let labels = payload.labels();
        assert_eq!(labels.status, "Status: Waiting for approval");
        assert_eq!(labels.task, "Current task: active");
        assert_eq!(labels.approval, "Pending approval: yes");
        let all = format!("{labels:?}").to_lowercase();
        assert!(!all.contains("transcript"));
        assert!(!all.contains("token"));
    }
}
