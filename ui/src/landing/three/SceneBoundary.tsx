// Any failure in a Level 3 scene (chunk fetch, WebGL context, texture upload) renders nothing, so
// the Level 2 version underneath simply stays visible.
import { Component, type ReactNode } from 'react'

export class SceneBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  render() {
    return this.state.failed ? null : this.props.children
  }
}
