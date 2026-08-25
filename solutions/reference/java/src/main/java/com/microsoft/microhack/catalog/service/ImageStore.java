package com.microsoft.microhack.catalog.service;

import java.io.IOException;
import java.util.Optional;

/** Reads canonical catalog image keys from the selected durable provider. */
public interface ImageStore {

    /** Returns exact PNG bytes or an empty value when the canonical object is absent. */
    Optional<byte[]> read(String key) throws IOException;
}
