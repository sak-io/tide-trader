// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import CredentialsForm from './CredentialsForm'

afterEach(cleanup)

function fillAndSubmit(keyId: string, secret: string): void {
  fireEvent.change(screen.getByPlaceholderText('PK...'), { target: { value: keyId } })
  fireEvent.change(screen.getByPlaceholderText('Secret key'), { target: { value: secret } })
  fireEvent.click(screen.getByRole('button', { name: /connect/i }))
}

describe('CredentialsForm', () => {
  beforeEach(() => {
    ;(
      window as unknown as {
        alpaca: { saveCredentials: ReturnType<typeof vi.fn>; getEncryptionStatus: ReturnType<typeof vi.fn> }
      }
    ).alpaca = {
      saveCredentials: vi.fn(),
      getEncryptionStatus: vi.fn().mockResolvedValue(true)
    }
  })

  it('trims and submits credentials, then reports success via onSaved', async () => {
    const saveCredentials = vi.fn().mockResolvedValue({ success: true })
    window.alpaca.saveCredentials = saveCredentials
    const onSaved = vi.fn()

    render(<CredentialsForm onSaved={onSaved} />)
    fillAndSubmit('  PKTEST123  ', '  supersecret  ')

    await waitFor(() => expect(onSaved).toHaveBeenCalledWith('PKTEST123'))
    expect(saveCredentials).toHaveBeenCalledWith({ keyId: 'PKTEST123', secret: 'supersecret' })
  })

  it('shows the returned error and does not call onSaved when validation fails', async () => {
    window.alpaca.saveCredentials = vi.fn().mockResolvedValue({
      success: false,
      error: 'Alpaca rejected these keys (unauthorized).'
    })
    const onSaved = vi.fn()

    render(<CredentialsForm onSaved={onSaved} />)
    fillAndSubmit('PKBAD', 'wrongsecret')

    expect(await screen.findByText('Alpaca rejected these keys (unauthorized).')).toBeInTheDocument()
    expect(onSaved).not.toHaveBeenCalled()
  })

  it('falls back to a generic error message when none is provided', async () => {
    window.alpaca.saveCredentials = vi.fn().mockResolvedValue({ success: false })

    render(<CredentialsForm onSaved={vi.fn()} />)
    fillAndSubmit('PKBAD', 'wrongsecret')

    expect(await screen.findByText('Could not verify these keys with Alpaca.')).toBeInTheDocument()
  })

  it('warns when OS-level encryption is unavailable', async () => {
    window.alpaca.getEncryptionStatus = vi.fn().mockResolvedValue(false)

    render(<CredentialsForm onSaved={vi.fn()} />)

    expect(
      await screen.findByText(/keys will be saved in plain text/i)
    ).toBeInTheDocument()
  })

  it('does not warn when OS-level encryption is available', async () => {
    window.alpaca.getEncryptionStatus = vi.fn().mockResolvedValue(true)

    render(<CredentialsForm onSaved={vi.fn()} />)

    await waitFor(() => expect(window.alpaca.getEncryptionStatus).toHaveBeenCalled())
    expect(screen.queryByText(/plain text/i)).not.toBeInTheDocument()
  })
})
